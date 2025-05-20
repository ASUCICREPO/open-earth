##############################################################################
#  Natural-Forest Classification Lambda
#  – complete file, ready for Lambda Function URL (payload format v2)
##############################################################################

import ee
import json
import datetime
import requests
import io
from PIL import Image, ImageDraw
import boto3
import os
import time
from functools import lru_cache
from shapely import wkt
from shapely.geometry import Polygon, MultiPolygon, box
import math
import concurrent.futures
import uuid

# ---------------------------------------------------------------------------
#  AWS clients & ENVIRONMENT VARIABLES
# ---------------------------------------------------------------------------
s3 = boto3.client('s3')

S3_BUCKET           = os.environ['S3_BUCKET']
ASSETS_BUCKET       = os.environ['ASSETS_BUCKET']
EE_KEY_PATH         = os.environ['EE_KEY_PATH']          # /tmp/service_account.json
DATA_PATH           = os.environ['DATA_PATH']            # /tmp/user_data.json
EE_KEY_S3_KEY       = os.environ['EE_KEY_S3_KEY']        # path inside ASSETS_BUCKET
OUTPUT_PREFIX       = os.environ['OUTPUT_PREFIX']
UPLOAD_EXPIRATION   = int(os.environ['UPLOAD_EXPIRATION'])
DOWNLOAD_EXPIRATION = int(os.environ['DOWNLOAD_EXPIRATION'])
ALLOWED_ORIGINS     = os.environ.get('ALLOWED_ORIGINS', '*').split(',')
DEBUG               = os.environ.get('DEBUG', 'false').lower() == 'true'

# ---------------------------------------------------------------------------
#  GLOBALS used by helper routines
# ---------------------------------------------------------------------------
ENTIRE_EE_BOUNDARY: ee.Geometry | None = None
CORRECT_AREA = 0.0
total_shapely_polygon = None
boundary_box          = None

# ---------------------------------------------------------------------------
#  🔐  CORS UTILITIES
# ---------------------------------------------------------------------------
def _build_cors_headers(request_headers: dict | None) -> dict:
    """
    Build CORS headers dynamically.

    • Echo back the request's Origin iff it appears in ALLOWED_ORIGINS.
    • Otherwise use the first allowed origin (or '*').
    """
    origin = (request_headers or {}).get('origin') or (request_headers or {}).get('Origin')
    allow_origin = (
        origin if origin and origin in ALLOWED_ORIGINS
        else ALLOWED_ORIGINS[0] if ALLOWED_ORIGINS and ALLOWED_ORIGINS[0]
        else '*'
    )
    return {
        'Access-Control-Allow-Origin':      allow_origin,
        'Access-Control-Allow-Methods':     'GET,POST,OPTIONS',
        'Access-Control-Allow-Headers':     'Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token',
        'Access-Control-Max-Age':           '600',
        # Include if you need cookies or Authorization headers in the browser:
        'Access-Control-Allow-Credentials': 'true',
    }

def _http_method(event: dict) -> str:
    """Return the HTTP verb for either REST (v1) or Function-URL/HTTP-API (v2) payloads."""
    return (
        event.get('httpMethod')                                  # REST API (proxy)
        or event.get('requestContext', {}).get('http', {}).get('method')  # HTTP API / Function URL
        or ''
    ).upper()

# ---------------------------------------------------------------------------
#  LAMBDA HANDLER
# ---------------------------------------------------------------------------
def lambda_handler(event, context):
    # ----------------------------------------------------------
    #  1. OPTIONS pre-flight   (must return *before* any work)
    # ----------------------------------------------------------
    if _http_method(event) == 'OPTIONS':
        return {
            'statusCode': 204,                  # 'No Content'
            'headers': _build_cors_headers(event.get('headers')),
            'body': ''
        }

    try:
        # ------------------------------------------------------
        #  2. Parse body & dispatch operation
        # ------------------------------------------------------
        request_body = parse_request_body(event)
        operation    = request_body.get('operation', '').lower()

        # ──────────────────────────────────────────────────────
        #  UPLOAD: create pre-signed PUT URL
        # ──────────────────────────────────────────────────────
        if operation == 'upload':
            filename = request_body.get('filename', f"user_data_{uuid.uuid4()}.json")
            if not filename.endswith('.json'):
                filename += '.json'
            filename  = sanitize_filename(filename)
            s3_key    = f"uploads/{filename}"

            presigned_url = generate_presigned_url(
                'put_object',
                {'Bucket': S3_BUCKET, 'Key': s3_key, 'ContentType': 'application/json'},
                UPLOAD_EXPIRATION
            )

            return {
                'statusCode': 200,
                'headers': _build_cors_headers(event.get('headers')),
                'body': json.dumps({'status':'success','upload_url':presigned_url,'filename':filename})
            }

        # ──────────────────────────────────────────────────────
        #  ANALYSIS
        # ──────────────────────────────────────────────────────
        elif operation == 'analysis':
            start_date   = request_body.get('start_date')
            end_date     = request_body.get('end_date')
            output_prefix= request_body.get('output_prefix', OUTPUT_PREFIX)
            filename     = request_body.get('filename')

            if not filename:
                return {
                    'statusCode': 400,
                    'headers': _build_cors_headers(event.get('headers')),
                    'body': json.dumps({'status':'error','message':'Filename is required for analysis'})
                }

            # 2.1  Download required files
            s3.download_file(ASSETS_BUCKET, EE_KEY_S3_KEY, EE_KEY_PATH)
            s3.download_file(S3_BUCKET, f"uploads/{filename}", DATA_PATH)

            with open(EE_KEY_PATH) as f:
                service_account = json.load(f).get('client_email')
            if not service_account:
                raise ValueError('client_email missing in GEE key')

            credentials = ee.ServiceAccountCredentials(service_account, EE_KEY_PATH)
            ee.Initialize(credentials)

            output_dir = "/tmp/forest_classification"
            os.makedirs(output_dir, exist_ok=True)

            result = process_natural_forest_classification(
                DATA_PATH, start_date, end_date, output_dir
            )
            if not result:
                return {
                    'statusCode': 400,
                    'headers': _build_cors_headers(event.get('headers')),
                    'body': json.dumps({'status':'error','message':'Cloud cover too high—try another range'})
                }

            image_file, stats_file, image_date = result

            # 2.2  Upload results
            minx,miny,maxx,maxy = boundary_box.bounds
            center_lat = round((miny+maxy)/2, 2)
            center_lon = round((minx+maxx)/2, 2)
            lat_long   = f"{center_lat:+.2f}{center_lon:+.2f}"

            s3_image_key = f"{output_prefix}/{image_date}-{lat_long}-natural_forest_classification.png"
            s3_stats_key = f"{output_prefix}/{image_date}-{lat_long}-natural_forest_stats.json"

            s3.upload_file(image_file, S3_BUCKET, s3_image_key, ExtraArgs={'ContentType':'image/png'})
            s3.upload_file(stats_file, S3_BUCKET, s3_stats_key)

            image_download_url = generate_presigned_url(
                'get_object',
                {
                    'Bucket': S3_BUCKET,
                    'Key':    s3_image_key,
                    'ResponseContentType':       'image/png',
                    'ResponseContentDisposition':f'attachment; filename="{os.path.basename(s3_image_key)}"'
                },
                DOWNLOAD_EXPIRATION
            )
            with open(stats_file) as f:
                stats_data = json.load(f)

            return {
                'statusCode': 200,
                'headers': _build_cors_headers(event.get('headers')),
                'body': json.dumps({
                    'status':'success',
                    'image_download_url': image_download_url,
                    'image_date':         image_date,
                    'analysis_results':   stats_data
                })
            }

        # ──────────────────────────────────────────────────────
        #  Unknown operation
        # ──────────────────────────────────────────────────────
        else:
            return {
                'statusCode': 400,
                'headers': _build_cors_headers(event.get('headers')),
                'body': json.dumps({
                    'status':'error',
                    'body':  request_body,
                    'message': f"Unknown operation '{operation}'. Use 'upload' or 'analysis'."
                })
            }

    # ----------------------------------------------------------
    #  3. Error handling
    # ----------------------------------------------------------
    except Exception as exc:
        import traceback
        trace = traceback.format_exc()
        print(trace)
        return {
            'statusCode': 500,
            'headers': _build_cors_headers(event.get('headers')),
            'body': json.dumps({'status':'error','message':str(exc),'trace':trace if DEBUG else None})
        }

# ============================================================================
#  HELPER FUNCTIONS  (mostly unchanged)
# ============================================================================
def parse_request_body(event):
    if 'body' not in event:
        return {}
    body = event['body']
    if body is None:
        return {}
    if isinstance(body, str):
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {}
    return body

def sanitize_filename(filename):
    filename = os.path.basename(filename)
    safe_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    return ''.join(c if c in safe_chars else '_' for c in filename)

def generate_presigned_url(operation, params, expiration=3600):
    return s3.generate_presigned_url(ClientMethod=operation, Params=params, ExpiresIn=expiration)

# ---------------------------------------------------------------------------
#  MAIN ANALYSIS ROUTINES  (identical to your original logic)
# ---------------------------------------------------------------------------
def process_natural_forest_classification(json_path, start_date, end_date, output_dir):
    start_time = time.time()

    global ENTIRE_EE_BOUNDARY, total_shapely_polygon, boundary_box
    total_shapely_polygon, boundary_box = load_boundary(json_path)
    ENTIRE_EE_BOUNDARY = shapely_to_ee(total_shapely_polygon.wkt)

    # Sentinel-2 filtering
    s2 = (
        ee.ImageCollection('COPERNICUS/S2_HARMONIZED')
        .filterDate(start_date, end_date)
        .filterBounds(ENTIRE_EE_BOUNDARY)
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 35))
        .sort('CLOUDY_PIXEL_PERCENTAGE')
    )

    if s2.size().getInfo() == 0:
        print("No Sentinel-2 images found.")
        return None

    first_image  = ee.Image(s2.first())
    cloud_cover  = first_image.get('CLOUDY_PIXEL_PERCENTAGE').getInfo()
    if cloud_cover > 1:
        print("Cloud cover too high.")
        return None

    image_date = ee.Date(first_image.get('system:time_start')).format('YYYY-MM-dd').getInfo()

    # Dynamic World
    dw_collection = (
        ee.ImageCollection('GOOGLE/DYNAMICWORLD/V1')
        .filterDate(start_date, end_date)
        .filterBounds(ENTIRE_EE_BOUNDARY)
    )
    if dw_collection.size().getInfo() == 0:
        print("No Dynamic World images found.")
        return None

    dw_image = dw_collection.select('label').mode()

    # Protected-area mask
    protected_areas = get_protected_areas(total_shapely_polygon.wkt, image_date)

    tree_mask           = dw_image.eq(1)
    natural_forest_mask = tree_mask.And(protected_areas)
    enhanced_classification = dw_image.rename('classification').where(natural_forest_mask, 10)

    # Stats & imagery
    stats_data, stats_file = calculate_area_statistics(
        enhanced_classification, ENTIRE_EE_BOUNDARY, CORRECT_AREA, image_date, output_dir
    )
    image_file = process_and_export_image(enhanced_classification, image_date, output_dir)

    print(f"Execution time: {time.time() - start_time:.2f}s")
    return image_file, stats_file, image_date

# ----------------------  (the rest of your helper functions)  ---------------
def split_boundary_box(boundary_box, max_size_km=30):
    minx, miny, maxx, maxy = boundary_box.bounds
    lat_mid = (miny + maxy) / 2
    km_per_deg_lon = 111 * math.cos(math.radians(lat_mid))
    km_per_deg_lat = 111

    width_km  = (maxx - minx) * km_per_deg_lon
    height_km = (maxy - miny) * km_per_deg_lat

    if width_km <= max_size_km and height_km <= max_size_km:
        return [boundary_box]

    if width_km * height_km > 1000:
        max_size_km = min(60, max(30, max_size_km))

    num_x = math.ceil(width_km  / max_size_km)
    num_y = math.ceil(height_km / max_size_km)
    step_x = (maxx - minx) / num_x
    step_y = (maxy - miny) / num_y

    sub_rectangles = []
    for i in range(num_x):
        for j in range(num_y):
            sub_minx = minx + i * step_x
            sub_maxx = minx + (i + 1) * step_x
            sub_miny = miny + j * step_y
            sub_maxy = miny + (j + 1) * step_y
            rect = box(sub_minx, sub_miny, sub_maxx, sub_maxy)
            if rect.intersects(total_shapely_polygon):
                sub_rectangles.append(rect)
    return sub_rectangles

def export_sub_polygon_as_png(image, boundary, max_retries=3):
    colors = {
        0:[65,155,223],1:[57,125,73],2:[136,176,83],3:[122,135,198],4:[228,150,53],
        5:[223,195,90],6:[196,40,27],7:[165,155,143],8:[179,159,225],9:[0,0,0],10:[0,64,0]
    }
    r_band = ee.Image(0).toByte().rename('red')
    g_band = ee.Image(0).toByte().rename('green')
    b_band = ee.Image(0).toByte().rename('blue')
    for class_val, color in colors.items():
        mask = image.eq(class_val)
        r_band = r_band.where(mask, color[0])
        g_band = g_band.where(mask, color[1])
        b_band = b_band.where(mask, color[2])
    rgb = ee.Image.cat([r_band, g_band, b_band]).unmask(0)

    for retry in range(max_retries):
        try:
            url = rgb.getDownloadURL({'region': boundary, 'scale':20, 'format':'png', 'maxPixels':1e9})
            resp = requests.get(url, timeout=120)
            if resp.status_code == 200:
                return Image.open(io.BytesIO(resp.content)).convert('RGB')
            print(f"Download failed ({resp.status_code}) retry {retry+1}")
            time.sleep(2)
        except Exception as e:
            print(f"Download error {e}, retry {retry+1}")
            time.sleep(2)
    return None

def process_sub_polygon(args):
    index, shapely_rect, enhanced_cls, image_date = args
    ee_rect = shapely_to_ee(shapely_rect.wkt)
    clipped  = enhanced_cls.clip(ee_rect)
    img      = export_sub_polygon_as_png(clipped, ee_rect)
    if img is None:
        return None
    return {'index':index,'png_image':img,'shapely_sub_rect':shapely_rect}

def create_boundary_mask(shapely_polygon, minx, miny, maxx, maxy, w_px, h_px):
    mask = Image.new('L', (w_px,h_px), 0)
    draw = ImageDraw.Draw(mask)
    def geo2px(lon,lat):
        x = int((lon - minx) / (maxx - minx) * w_px)
        y = int((maxy - lat) / (maxy - miny) * h_px)
        return max(0,min(x,w_px-1)), max(0,min(y,h_px-1))
    if isinstance(shapely_polygon, MultiPolygon):
        for poly in shapely_polygon.geoms:
            px_coords = [geo2px(lon,lat) for lon,lat in poly.exterior.coords]
            draw.polygon(px_coords, fill=255)
    else:
        px_coords = [geo2px(lon,lat) for lon,lat in shapely_polygon.exterior.coords]
        draw.polygon(px_coords, fill=255)
    return mask

def merge_images_properly(results, output_dir, image_date):
    results = [r for r in results if r]
    if not results:
        return None
    minx,miny,maxx,maxy = boundary_box.bounds
    lat_mid  = (miny+maxy)/2
    m_per_deg_lon = 111000 * math.cos(math.radians(lat_mid))
    m_per_deg_lat = 111000
    w_m = (maxx-minx)*m_per_deg_lon
    h_m = (maxy-miny)*m_per_deg_lat
    scale = 10
    if w_m*h_m > 1e9:
        scale = 20
    w_px = int(w_m/scale)
    h_px = int(h_m/scale)
    max_dim = 5000
    if w_px > max_dim or h_px > max_dim:
        factor = max(w_px/max_dim, h_px/max_dim)
        w_px = int(w_px/factor)
        h_px = int(h_px/factor)

    merged = Image.new('RGB', (w_px,h_px), (0,0,0))
    def geo2px(lon,lat):
        x = int((lon - minx)/(maxx-minx)*w_px)
        y = int((maxy - lat)/(maxy-miny)*h_px)
        return x,y
    for res in results:
        sub = res['png_image']
        rect= res['shapely_sub_rect']
        smx,smy,sex,sey = rect.bounds
        x1,y1 = geo2px(smx,sey)
        x2,y2 = geo2px(sex,smy)
        if x2-x1 <=0 or y2-y1 <=0:
            continue
        merged.paste(sub.resize((x2-x1,y2-y1), Image.Resampling.LANCZOS), (x1,y1))

    mask = create_boundary_mask(total_shapely_polygon, minx,miny,maxx,maxy,w_px,h_px)
    composite = Image.composite(merged, Image.new('RGB', merged.size, (0,0,0)), mask)

    center_lat = round((miny+maxy)/2,2)
    center_lon = round((minx+maxx)/2,2)
    lat_long   = f"{center_lat:+.2f}{center_lon:+.2f}"
    outfile    = os.path.join(output_dir, f"{image_date}-{lat_long}-natural_forest_classification.png")
    create_final_image_with_legend(composite, outfile, image_date)
    return outfile

def process_and_export_image(enhanced_cls, image_date, output_dir):
    sub_rects = split_boundary_box(boundary_box, max_size_km=30)
    args = [(i,r,enhanced_cls,image_date) for i,r in enumerate(sub_rects)]
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(10,len(sub_rects))) as ex:
        futures=[ex.submit(process_sub_polygon, a) for a in args]
        for f in concurrent.futures.as_completed(futures):
            try:
                res=f.result()
                if res:
                    results.append(res)
                    print(f"Processed sub-rect {res['index']+1}/{len(sub_rects)}")
            except Exception as e:
                print(f"Error in sub-rect: {e}")
    return merge_images_properly(results, output_dir, image_date)

def load_boundary(json_path):
    with open(json_path) as f:
        data=json.load(f)
    json_area = data.get('area',0)
    print(f"JSON area: {json_area:.2f} km²")
    polygon  = wkt.loads(data['city_geometry'])
    bbox     = box(data['bbox_west'],data['bbox_south'],data['bbox_east'],data['bbox_north'])
    global CORRECT_AREA
    CORRECT_AREA = json_area
    return polygon, bbox

@lru_cache(maxsize=128)
def shapely_to_ee(poly_wkt):
    poly = wkt.loads(poly_wkt)
    if isinstance(poly, MultiPolygon):
        multi = [[list(p.exterior.coords)]+[list(r.coords) for r in p.interiors] for p in poly.geoms]
        return ee.Geometry.MultiPolygon(multi)
    exterior=list(poly.exterior.coords)
    interiors=[list(r.coords) for r in poly.interiors]
    return ee.Geometry.Polygon([exterior]+interiors)

@lru_cache(maxsize=32)
def get_protected_areas(boundary_wkt, target_date_str):
    boundary = shapely_to_ee(boundary_wkt)
    if isinstance(target_date_str, str):
        dt = datetime.datetime.strptime(target_date_str, '%Y-%m-%d')
    else:
        dt = datetime.datetime.strptime(target_date_str.format('YYYY-MM-dd').getInfo(), '%Y-%m-%d')
    yyyymm = dt.strftime('%Y%m')
    wdpa_path = f'WCMC/WDPA/{yyyymm}/polygons'
    try:
        wdpa = ee.FeatureCollection(wdpa_path)
        print(f"Using WDPA {yyyymm}")
    except Exception:
        print("Fallback to current WDPA data")
        wdpa = ee.FeatureCollection('WCMC/WDPA/current/polygons')
    pa_mask = wdpa.filterBounds(boundary).reduceToImage(
        properties=['WDPAID'], reducer=ee.Reducer.firstNonNull()
    ).gt(0).rename('protected')
    return pa_mask.clip(boundary)

def create_final_image_with_legend(map_img, output_file, image_date):
    colors=[(65,155,223),(57,125,73),(136,176,83),(122,135,198),(228,150,53),
            (223,195,90),(196,40,27),(165,155,143),(179,159,225),(0,0,0),(0,64,0)]
    labels=['Water','Trees','Grass','Flooded Vegetation','Crops',
            'Shrub & Scrub','Built','Bare','Snow & Ice','Cloud','Natural Forest']
    mw,mh = map_img.size
    legend_w=200
    legend_h=len(labels)*30+20
    final_w = mw+legend_w+20
    final_h = max(mh,legend_h)+60
    final = Image.new('RGB',(final_w,final_h),(255,255,255))
    final.paste(map_img,(10,50))
    draw = ImageDraw.Draw(final)
    draw.text((10,10), f"Natural Forest Classification ({image_date})", fill=(0,0,0))
    lx = mw+20
    ly = 50
    for i,(col,label) in enumerate(zip(colors,labels)):
        rect_y = ly+i*30
        draw.rectangle([lx,rect_y,lx+20,rect_y+20], fill=col)
        draw.text((lx+30,rect_y+5), label, fill=(0,0,0))
    final.save(output_file)
    return output_file

def calculate_area_statistics(image, boundary, total_area, image_date, output_dir):
    CLASS_NAMES=['water','trees','grass','flooded_vegetation','crops','shrub_and_scrub',
                 'built','bare','snow_and_ice','cloud','natural_forest']
    hist = image.reduceRegion(
        reducer=ee.Reducer.frequencyHistogram(),
        geometry=boundary, scale=10, maxPixels=1e13, bestEffort=True, tileScale=4
    ).get('classification').getInfo() or {}

    totals = {CLASS_NAMES[int(k)]:v for k,v in hist.items() if int(k)<len(CLASS_NAMES)}
    pixel_sum = sum(totals.values())
    areas={}
    for k,v in totals.items():
        areas[k]=round((v/pixel_sum)*total_area,5) if pixel_sum else 0.0
    for name in CLASS_NAMES:
        areas.setdefault(name,0.0)

    nf_area=areas['natural_forest']
    tree_area=areas['trees']
    total_forest=nf_area+tree_area
    stats={
        "date":image_date,
        "total_area_km2":round(total_area,5),
        "forest_area_km2":round(total_forest,5),
        "natural_forest_km2":round(nf_area,5),
        "natural_forest_percentage":round((nf_area/total_forest)*100,5) if total_forest else 0,
        "other_trees_km2":round(tree_area,5),
        "other_trees_percentage":round((tree_area/total_forest)*100,5) if total_forest else 0,
        "land_cover_classes":{}
    }
    for name,val in sorted(areas.items(), key=lambda x:x[1], reverse=True):
        if val>0:
            stats["land_cover_classes"][name]={
                "area_km2":val,
                "percentage":round((val/total_area)*100,5) if total_area else 0
            }
    stats_file=os.path.join(output_dir,f"natural_forest_stats_{image_date}.json")
    with open(stats_file,'w') as f:
        json.dump(stats,f,indent=2)
    return stats,stats_file
