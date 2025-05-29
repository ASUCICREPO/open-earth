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

# --- AWS S3 Initialization ---
s3 = boto3.client('s3')  # Initialize the S3 client for interacting with AWS S3 buckets

# --- Environment Variables ---
# These variables are fetched from the Lambda environment for configuration
S3_BUCKET = os.environ['S3_BUCKET']  # Bucket for storing user uploads and results
ASSETS_BUCKET = os.environ['ASSETS_BUCKET']  # Bucket for static assets like credentials
EE_KEY_PATH = os.environ['EE_KEY_PATH']  # Local path for Earth Engine credentials
DATA_PATH = os.environ['DATA_PATH']  # Local path for user-uploaded data
EE_KEY_S3_KEY = os.environ['EE_KEY_S3_KEY']  # S3 key for Earth Engine credentials
OUTPUT_PREFIX = os.environ['OUTPUT_PREFIX']  # Prefix for output files in S3
UPLOAD_EXPIRATION = int(os.environ['UPLOAD_EXPIRATION'])  # Expiration time for upload URLs
DOWNLOAD_EXPIRATION = int(os.environ['DOWNLOAD_EXPIRATION'])  # Expiration time for download URLs
ALLOWED_ORIGINS = os.environ['ALLOWED_ORIGINS'].split(',')  # List of allowed CORS origins
DEBUG = os.environ['DEBUG'].lower() == 'true'  # Debug mode flag

# --- Global Variables ---
# Used across functions for Earth Engine processing
ENTIRE_EE_BOUNDARY = None  # Earth Engine geometry for the entire boundary
CORRECT_AREA = 0  # Total area from user data in square kilometers
total_shapely_polygon = None  # Shapely polygon for the boundary
boundary_box = None  # Bounding box for the boundary

# --- CORS Utilities ---
def _build_cors_headers(request_headers: dict | None) -> dict:
    """
    Build CORS headers dynamically based on the request's origin.
    Ensures secure cross-origin requests by validating against ALLOWED_ORIGINS.
    """
    origin = (request_headers or {}).get('origin') or (request_headers or {}).get('Origin')
    allow_origin = (
        origin if origin and origin in ALLOWED_ORIGINS
        else ALLOWED_ORIGINS[0] if ALLOWED_ORIGINS and ALLOWED_ORIGINS[0]
        else '*'
    )
    return {
        'Access-Control-Allow-Origin': allow_origin,
        'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token',
        'Access-Control-Max-Age': '600',
    }

def _http_method(event: dict) -> str:
    """Extract the HTTP method from the event, supporting both v1 and v2 AWS payloads."""
    return (
        event.get('httpMethod')
        or event.get('requestContext', {}).get('http', {}).get('method')
        or ''
    ).upper()

# --- Main Lambda Handler ---
def lambda_handler(event, context):
    """
    Main entry point for the AWS Lambda function.
    Handles two operations: 'upload' (generates S3 pre-signed URL) and 'analysis' (processes Earth Engine data).
    """
    # Handle CORS preflight OPTIONS request
    if _http_method(event) == 'OPTIONS':
        return {
            'statusCode': 204,
            'headers': _build_cors_headers(event.get('headers')),
            'body': ''
        }

    try:
        request_body = parse_request_body(event)
        operation = request_body.get('operation', '').lower()

        # --- Upload Operation ---
        if operation == 'upload':
            filename = request_body.get('filename', f"user_data_{uuid.uuid4()}.json")
            if not filename.endswith('.json'):
                filename += '.json'
            filename = sanitize_filename(filename)  # Ensure filename is safe
            s3_key = f"uploads/{filename}"

            # Generate a pre-signed URL for uploading to S3
            presigned_url = generate_presigned_url(
                'put_object',
                {'Bucket': S3_BUCKET, 'Key': s3_key, 'ContentType': 'application/json'},
                UPLOAD_EXPIRATION
            )

            return {
                'statusCode': 200,
                'headers': _build_cors_headers(event.get('headers')),
                'body': json.dumps({
                    'status': 'success',
                    'upload_url': presigned_url,
                    'filename': filename
                })
            }

        # --- Analysis Operation ---
        elif operation == 'analysis':
            start_date = request_body.get('start_date')
            end_date = request_body.get('end_date')
            output_prefix = request_body.get('output_prefix', OUTPUT_PREFIX)
            filename = request_body.get('filename')

            if not filename:
                return {
                    'statusCode': 400,
                    'headers': _build_cors_headers(event.get('headers')),
                    'body': json.dumps({
                        'status': 'error',
                        'message': 'Filename is required for analysis'
                    })
                }

            # Download necessary files from S3
            s3.download_file(ASSETS_BUCKET, EE_KEY_S3_KEY, EE_KEY_PATH)  # Earth Engine credentials
            user_data_key = f"uploads/{filename}"
            s3.download_file(S3_BUCKET, user_data_key, DATA_PATH)  # User data

            # Initialize Earth Engine with credentials
            with open(EE_KEY_PATH, 'r') as f:
                gee_credentials = json.load(f)
                service_account = gee_credentials.get('client_email')
                if not service_account:
                    raise ValueError("client_email not found in GEE credentials file")
            credentials = ee.ServiceAccountCredentials(service_account, EE_KEY_PATH)
            ee.Initialize(credentials)
            print('Earth Engine initialized successfully')

            # Set up output directory
            output_dir = "/tmp/forest_classification"
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)

            # Process the natural forest classification
            result = process_natural_forest_classification(DATA_PATH, start_date, end_date, output_dir)
            if not result:
                return {
                    'statusCode': 400,
                    'headers': _build_cors_headers(event.get('headers')),
                    'body': json.dumps({
                        'status': 'error',
                        'message': 'Cloud cover is too much, please try another date range'
                    })
                }

            image_file, stats_file, image_date = result

            # Generate unique file names using the boundary center
            minx, miny, maxx, maxy = boundary_box.bounds
            center_lat = round((miny + maxy) / 2, 2)
            center_lon = round((minx + maxx) / 2, 2)
            lat_long = f"{center_lat:+.2f}{center_lon:+.2f}"

            # Upload results to S3
            s3_image_key = f"{output_prefix}/{image_date}-{lat_long}-natural_forest_classification.png"
            s3_stats_key = f"{output_prefix}/{image_date}-{lat_long}-natural_forest_stats.json"
            s3.upload_file(image_file, S3_BUCKET, s3_image_key, ExtraArgs={'ContentType': 'image/png'})
            s3.upload_file(stats_file, S3_BUCKET, s3_stats_key)

            # Generate a pre-signed URL for downloading the image
            image_download_url = generate_presigned_url(
                'get_object',
                {
                    'Bucket': S3_BUCKET,
                    'Key': s3_image_key,
                    'ResponseContentType': 'image/png',
                    'ResponseContentDisposition': f'attachment; filename="{image_date}-{lat_long}-natural_forest_classification.png"'
                },
                DOWNLOAD_EXPIRATION
            )

            # Load stats data to return to the client
            with open(stats_file, 'r') as f:
                stats_data = json.load(f)

            return {
                'statusCode': 200,
                'headers': _build_cors_headers(event.get('headers')),
                'body': json.dumps({
                    'status': 'success',
                    'image_download_url': image_download_url,
                    'image_date': image_date,
                    'analysis_results': stats_data
                })
            }

        else:
            return {
                'statusCode': 400,
                'headers': _build_cors_headers(event.get('headers')),
                'body': json.dumps({
                    'status': 'error',
                    'body': request_body,
                    'message': f"Unknown operation: {operation}. Valid operations are 'upload' or 'analysis'."
                })
            }

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(error_trace)
        return {
            'statusCode': 500,
            'headers': _build_cors_headers(event.get('headers')),
            'body': json.dumps({
                'status': 'error',
                'message': str(e),
                'trace': error_trace if DEBUG else None
            })
        }

# --- Helper Functions ---
def parse_request_body(event):
    """Parse the request body from the Lambda event, handling various formats."""
    if 'body' not in event or event['body'] is None:
        return {}
    body = event['body']
    return json.loads(body) if isinstance(body, str) else body

def sanitize_filename(filename):
    """Clean the filename to prevent security issues like directory traversal."""
    filename = os.path.basename(filename)
    safe_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    return ''.join(c if c in safe_chars else '_' for c in filename)

def generate_presigned_url(operation, params, expiration=3600):
    """Generate a pre-signed URL for S3 operations like upload or download."""
    try:
        return s3.generate_presigned_url(ClientMethod=operation, Params=params, ExpiresIn=expiration)
    except Exception as e:
        print(f"Error generating presigned URL: {e}")
        raise

# --- Earth Engine Processing ---
def process_natural_forest_classification(json_path, start_date, end_date, output_dir):
    """
    Process natural forest classification using Earth Engine data.
    Combines Sentinel-2 and Dynamic World data to classify forests and calculate statistics.
    """
    start_time = time.time()
    global ENTIRE_EE_BOUNDARY, total_shapely_polygon, boundary_box
    total_shapely_polygon, boundary_box = load_boundary(json_path)
    ENTIRE_EE_BOUNDARY = shapely_to_ee(total_shapely_polygon.wkt)

    # Filter Sentinel-2 imagery for low cloud cover
    s2 = (ee.ImageCollection('COPERNICUS/S2_HARMONIZED')
          .filterDate(start_date, end_date)
          .filterBounds(ENTIRE_EE_BOUNDARY)
          .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 35))
          .sort('CLOUDY_PIXEL_PERCENTAGE'))
    
    if s2.size().getInfo() == 0:
        print("No Sentinel-2 images found in the date range.")
        return None
    
    first_image = ee.Image(s2.first())
    cloud_cover = first_image.get('CLOUDY_PIXEL_PERCENTAGE').getInfo()
    print(f"Lowest cloud cover percentage: {cloud_cover}%")
    if cloud_cover > 1:
        print("Cloud cover is too much, please try another range")
        return None
    
    image_date = ee.Date(first_image.get('system:time_start')).format('YYYY-MM-dd').getInfo()

    # Get Dynamic World land cover data
    dw_collection = (ee.ImageCollection('GOOGLE/DYNAMICWORLD/V1')
                     .filterDate(start_date, end_date)
                     .filterBounds(ENTIRE_EE_BOUNDARY))
    
    if dw_collection.size().getInfo() == 0:
        print("No Dynamic World images found for the given date range and boundary.")
        return None
    
    dw_image = dw_collection.select('label').mode()
    protected_areas = get_protected_areas(total_shapely_polygon.wkt, image_date)

    # Classify natural forests (trees in protected areas)
    tree_mask = dw_image.eq(1)
    natural_forest = tree_mask.And(protected_areas)
    enhanced_classification = dw_image.rename('classification').where(natural_forest, 10)

    print("Calculating area statistics...")
    stats_data, stats_file = calculate_area_statistics(enhanced_classification, ENTIRE_EE_BOUNDARY, CORRECT_AREA, image_date, output_dir)
    
    print("Processing image...")
    image_file = process_and_export_image(enhanced_classification, image_date, output_dir)
    
    print(f"Total execution time: {time.time() - start_time:.2f} seconds")
    return image_file, stats_file, image_date

# --- Boundary and Image Processing ---
def split_boundary_box(boundary_box, max_size_km=30):
    """Split large boundary boxes into smaller rectangles for Earth Engine processing."""
    minx, miny, maxx, maxy = boundary_box.bounds
    lat_mid = (miny + maxy) / 2
    km_per_deg_lon = 111 * math.cos(math.radians(lat_mid))
    km_per_deg_lat = 111
    width_km = (maxx - minx) * km_per_deg_lon
    height_km = (maxy - miny) * km_per_deg_lat

    if width_km <= max_size_km and height_km <= max_size_km:
        print("Boundary box is small enough, using single rectangle")
        return [boundary_box]

    if width_km * height_km > 1000:
        max_size_km = min(60, max(30, max_size_km))

    num_x = math.ceil(width_km / max_size_km)
    num_y = math.ceil(height_km / max_size_km)
    step_x, step_y = (maxx - minx) / num_x, (maxy - miny) / num_y
    sub_rectangles = []

    for i in range(num_x):
        for j in range(num_y):
            sub_rect = box(minx + i * step_x, miny + j * step_y, minx + (i + 1) * step_x, miny + (j + 1) * step_y)
            if sub_rect.intersects(total_shapely_polygon):
                sub_rectangles.append(sub_rect)
    return sub_rectangles

def export_sub_polygon_as_png(image, boundary, max_retries=3):
    """Export a classified sub-polygon as a colored PNG image from Earth Engine."""
    colors = {
        0: [65, 155, 223], 1: [57, 125, 73], 2: [136, 176, 83], 3: [122, 135, 198], 4: [228, 150, 53],
        5: [223, 195, 90], 6: [196, 40, 27], 7: [165, 155, 143], 8: [179, 159, 225], 9: [0, 0, 0], 10: [0, 64, 0]
    }
    r_band, g_band, b_band = [ee.Image(0).toByte().rename(c) for c in ['red', 'green', 'blue']]
    for value, color in colors.items():
        mask = image.eq(value)
        r_band, g_band, b_band = [band.where(mask, col) for band, col in zip([r_band, g_band, b_band], color)]
    rgb_image = ee.Image.cat([r_band, g_band, b_band]).unmask(0)

    for retry in range(max_retries):
        try:
            url = rgb_image.getDownloadURL({'region': boundary, 'scale': 20, 'format': 'png', 'maxPixels': 1e9})
            response = requests.get(url, timeout=120)
            if response.status_code == 200:
                return Image.open(io.BytesIO(response.content)).convert("RGB")
            print(f"Failed to download sub-rectangle image: {response.status_code}, retry {retry+1}/{max_retries}")
            time.sleep(2)
        except Exception as e:
            print(f"Error downloading image: {e}, retry {retry+1}/{max_retries}")
            time.sleep(2)
    return None

def process_sub_polygon(args):
    """Process a single sub-polygon and export it as a PNG image."""
    index, shapely_sub_rect, enhanced_classification, image_date = args
    ee_sub_rect = shapely_to_ee(shapely_sub_rect.wkt)
    forest_classification = enhanced_classification.clip(ee_sub_rect)
    class_png_image = export_sub_polygon_as_png(forest_classification, ee_sub_rect)
    if class_png_image is None:
        return None
    return {'index': index, 'image_date': image_date, 'png_image': class_png_image, 'shapely_sub_rect': shapely_sub_rect}

def create_boundary_mask(shapely_polygon, minx, miny, maxx, maxy, width_pixels, height_pixels):
    """Create a mask to outline the boundary polygon on the final image."""
    mask = Image.new('L', (width_pixels, height_pixels), 0)
    draw = ImageDraw.Draw(mask)
    def geo_to_pixel(lon, lat):
        x = int((lon - minx) / (maxx - minx) * width_pixels)
        y = int((maxy - lat) / (maxy - miny) * height_pixels)
        return max(0, min(x, width_pixels - 1)), max(0, min(y, height_pixels - 1))
    
    coords = [list(poly.exterior.coords) for poly in (shapely_polygon.geoms if isinstance(shapely_polygon, MultiPolygon) else [shapely_polygon])]
    for poly_coords in coords:
        pixel_coords = [geo_to_pixel(lon, lat) for lon, lat in poly_coords]
        draw.polygon(pixel_coords, fill=255)
    return mask

def merge_images_properly(results, output_dir, image_date):
    """Merge sub-rectangle images into a single cohesive image with a boundary mask."""
    results = [r for r in results if r and r.get('png_image')]
    if not results:
        print("No valid sub-rectangle results to merge")
        return None
    
    minx, miny, maxx, maxy = boundary_box.bounds
    lat_mid = (miny + maxy) / 2
    meters_per_deg_lon, meters_per_deg_lat = 111000 * math.cos(math.radians(lat_mid)), 111000
    width_m, height_m = (maxx - minx) * meters_per_deg_lon, (maxy - miny) * meters_per_deg_lat
    scale_factor = 20 if width_m * height_m > 1e9 else 10
    width_pixels, height_pixels = [int(dim / scale_factor) for dim in (width_m, height_m)]
    
    max_dimension = 5000
    if width_pixels > max_dimension or height_pixels > max_dimension:
        scale_factor = max(width_pixels / max_dimension, height_pixels / max_dimension)
        width_pixels, height_pixels = int(width_pixels / scale_factor), int(height_m / scale_factor)
    
    merged_img = Image.new('RGB', (width_pixels, height_pixels), (0, 0, 0))
    def geo_to_pixel(lon, lat):
        x = int((lon - minx) / (maxx - minx) * width_pixels)
        y = int((maxy - lat) / (maxy - miny) * height_pixels)
        return max(0, min(x, width_pixels - 1)), max(0, min(y, height_pixels - 1))
    
    for result in results:
        sub_img, sub_rect = result['png_image'], result['shapely_sub_rect']
        sub_minx, sub_miny, sub_maxx, sub_maxy = sub_rect.bounds
        x1, y1 = geo_to_pixel(sub_minx, sub_maxy)
        x2, y2 = geo_to_pixel(sub_maxx, sub_miny)
        sub_width, sub_height = x2 - x1, y2 - y1
        if sub_width > 0 and sub_height > 0:
            resized_sub_img = sub_img.resize((sub_width, sub_height), Image.Resampling.LANCZOS)
            merged_img.paste(resized_sub_img, (x1, y1))
    
    boundary_mask = create_boundary_mask(total_shapely_polygon, minx, miny, maxx, maxy, width_pixels, height_pixels)
    masked_img = Image.composite(merged_img, Image.new('RGB', merged_img.size, (0, 0, 0)), boundary_mask)
    center_lat, center_lon = round((miny + maxy) / 2, 2), round((minx + maxx) / 2, 2)
    lat_long = f"{center_lat:+.2f}{center_lon:+.2f}"
    final_image_file = os.path.join(output_dir, f"{image_date}-{lat_long}-natural_forest_classification.png")
    create_final_image_with_legend(masked_img, final_image_file, image_date)
    return final_image_file

def process_and_export_image(enhanced_classification, image_date, output_dir):
    """Split the boundary, process sub-regions concurrently, and merge into a final image."""
    sub_rectangles = split_boundary_box(boundary_box, max_size_km=30)
    print(f"Processing {len(sub_rectangles)} sub-rectangles...")
    process_args = [(i, sub_rect, enhanced_classification, image_date) for i, sub_rect in enumerate(sub_rectangles)]
    
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, len(sub_rectangles))) as executor:
        futures = [executor.submit(process_sub_polygon, arg) for arg in process_args]
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                if result:
                    results.append(result)
                    print(f"Processed sub-rectangle {result['index']+1}/{len(sub_rectangles)}")
            except Exception as e:
                print(f"Error processing sub-rectangle: {e}")
    
    return merge_images_properly(results, output_dir, image_date) if results else None

def load_boundary(json_path):
    """Load boundary polygon and bounding box from the user-uploaded JSON file."""
    with open(json_path) as f:
        data = json.load(f)
    json_area = data.get('area', 0)
    print(f"Area from JSON file: {json_area:.2f} km²")
    wkt_polygon = data['city_geometry']
    polygon = wkt.loads(wkt_polygon)
    boundary_box = box(data['bbox_west'], data['bbox_south'], data['bbox_east'], data['bbox_north'])
    global CORRECT_AREA
    CORRECT_AREA = json_area
    return polygon, boundary_box

@lru_cache(maxsize=128)
def shapely_to_ee(poly_wkt):
    """Convert a Shapely polygon (WKT) to an Earth Engine geometry, with caching for performance."""
    poly = wkt.loads(poly_wkt)
    if isinstance(poly, MultiPolygon):
        multi_coords = [[list(p.exterior.coords)] + [list(r.coords) for r in p.interiors] for p in poly.geoms]
        return ee.Geometry.MultiPolygon(multi_coords)
    exterior = list(poly.exterior.coords)
    interiors = [list(r.coords) for r in poly.interiors]
    return ee.Geometry.Polygon([exterior] + interiors)

@lru_cache(maxsize=32)
def get_protected_areas(boundary_wkt, target_date_str):
    """Fetch protected areas from WDPA for the given boundary and date."""
    boundary = shapely_to_ee(boundary_wkt)
    dt = datetime.datetime.strptime(target_date_str, '%Y-%m-%d') if isinstance(target_date_str, str) else datetime.datetime.strptime(target_date_str.format('YYYY-MM-dd').getInfo(), '%Y-%m-%d')
    yyyymm = dt.strftime('%Y%m')
    wdpa_path = f'WCMC/WDPA/{yyyymm}/polygons'
    try:
        wdpa = ee.FeatureCollection(wdpa_path)
        print(f"Using WDPA {yyyymm}/polygons")
    except Exception:
        print("Falling back to current WDPA data")
        wdpa = ee.FeatureCollection('WCMC/WDPA/current/polygons')
    protected_areas = wdpa.filterBounds(boundary)
    return protected_areas.reduceToImage(properties=['WDPAID'], reducer=ee.Reducer.firstNonNull()).gt(0).rename('protected').clip(boundary)

def create_final_image_with_legend(map_img, output_file, image_date):
    """Add a legend to the classified image and save it."""
    colors = [
        (65, 155, 223), (57, 125, 73), (136, 176, 83), (122, 135, 198), (228, 150, 53),
        (223, 195, 90), (196, 40, 27), (165, 155, 143), (179, 159, 225), (0, 0, 0), (0, 64, 0)
    ]
    labels = ['Water', 'Trees', 'Grass', 'Flooded Vegetation', 'Crops', 'Shrub & Scrub', 'Built', 'Bare', 'Snow & Ice', 'Cloud', 'Natural Forest']
    map_width, map_height = map_img.size
    legend_width, legend_height = 200, len(labels) * 50 + 20
    final_width, final_height = map_width + legend_width + 20, max(map_height, legend_height) + 60
    
    final_img = Image.new('RGB', (final_width, final_height), (255, 255, 255))
    final_img.paste(map_img, (10, 50))
    draw = ImageDraw.Draw(final_img)
    draw.text((10, 10), f"Natural Forest Classification ({image_date})", fill=(0, 0, 0))
    
    legend_x, legend_y = map_width + 20, 50
    for i, (color, label) in enumerate(zip(colors, labels)):
        rect_y = legend_y + i * 30
        draw.rectangle([legend_x, rect_y, legend_x + 20, rect_y + 20], fill=color)
        draw.text((legend_x + 30, rect_y + 5), label, fill=(0, 0, 0))
    
    final_img.save(output_file)
    return output_file

def calculate_area_statistics(image, boundary, total_area, image_date, output_dir):
    """Calculate land cover statistics and save them to a JSON file."""
    CLASS_NAMES = ['water', 'trees', 'grass', 'flooded_vegetation', 'crops', 'shrub_and_scrub', 'built', 'bare', 'snow_and_ice', 'cloud', 'natural_forest']
    histogram = image.reduceRegion(reducer=ee.Reducer.frequencyHistogram(), geometry=boundary, scale=10, maxPixels=1e13, bestEffort=True, tileScale=4).get('classification').getInfo() or {}
    
    class_pixels, total_pixels = {}, 0
    for class_value, pixel_count in histogram.items():
        class_idx = int(class_value)
        if class_idx < len(CLASS_NAMES):
            class_pixels[CLASS_NAMES[class_idx]] = pixel_count
            total_pixels += pixel_count
    
    class_areas = {name: round((pixels / total_pixels) * total_area, 5) if total_pixels > 0 else 0.0 for name, pixels in class_pixels.items()}
    for name in CLASS_NAMES:
        if name not in class_areas:
            class_areas[name] = 0.0
    
    natural_forest_area, trees_area = class_areas['natural_forest'], class_areas['trees']
    total_forest_area = natural_forest_area + trees_area
    stats_data = {
        "date": image_date,
        "total_area_km2": round(total_area, 5),
        "forest_area_km2": round(total_forest_area, 5),
        "natural_forest_km2": round(natural_forest_area, 5),
        "natural_forest_percentage": round((natural_forest_area / total_forest_area) * 100, 5) if total_forest_area > 0 else 0,
        "other_trees_km2": round(trees_area, 5),
        "other_trees_percentage": round((trees_area / total_forest_area) * 100, 5) if total_forest_area > 0 else 0,
        "land_cover_classes": {name: {"area_km2": round(area, 5), "percentage": round((area / total_area) * 100, 5) if total_area > 0 else 0} 
                               for name, area in sorted(class_areas.items(), key=lambda x: x[1], reverse=True) if area > 0}
    }
    
    stats_file = os.path.join(output_dir, f"natural_forest_stats_{image_date}.json")
    with open(stats_file, 'w') as f:
        json.dump(stats_data, f, indent=2)
    return stats_data, stats_file