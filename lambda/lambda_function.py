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

# Initialize S3 client
s3 = boto3.client('s3')

# Get environment variables (no default values)
S3_BUCKET = os.environ['S3_BUCKET']
SERVICE_ACCOUNT = os.environ['SERVICE_ACCOUNT']
EE_KEY_PATH = os.environ['EE_KEY_PATH']
DATA_PATH = os.environ['DATA_PATH']
EE_KEY_S3_KEY = os.environ['EE_KEY_S3_KEY']
DATA_S3_KEY = os.environ['DATA_S3_KEY']
START_DATE = os.environ['START_DATE']
END_DATE = os.environ['END_DATE']
OUTPUT_PREFIX = os.environ['OUTPUT_PREFIX']
UPLOAD_EXPIRATION = int(os.environ['UPLOAD_EXPIRATION'])
DOWNLOAD_EXPIRATION = int(os.environ['DOWNLOAD_EXPIRATION'])
ALLOWED_ORIGINS = os.environ['ALLOWED_ORIGINS'].split(',')
DEBUG = os.environ['DEBUG'].lower() == 'true'

# Global variables
ENTIRE_EE_BOUNDARY = None
CORRECT_AREA = 0
total_shapely_polygon = None
boundary_box = None

def lambda_handler(event, context):
    try:
        # Add CORS headers for all responses
        cors_headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
        }
        
        # Parse request body
        request_body = parse_request_body(event)
        
        # Get operation type from request
        operation = request_body.get('operation', '').lower()
        
        if operation == 'upload':
            # Generate pre-signed URL for file upload
            filename = request_body.get('filename', f"user_data_{uuid.uuid4()}.json")
            
            # Ensure filename is sanitized and has .json extension
            if not filename.endswith('.json'):
                filename += '.json'
            
            filename = sanitize_filename(filename)
            s3_key = f"uploads/{filename}"
            
            # Generate pre-signed URL for upload
            presigned_url = generate_presigned_url(
                'put_object',
                {'Bucket': S3_BUCKET, 'Key': s3_key, 'ContentType': 'application/json'},
                UPLOAD_EXPIRATION
            )
            
            return {
                'statusCode': 200,
                'headers': cors_headers,
                'body': json.dumps({
                    'status': 'success',
                    'upload_url': presigned_url,
                    'filename': filename
                })
            }
            
        elif operation == 'analysis':
            # Get parameters for analysis
            start_date = request_body.get('start_date', START_DATE)
            end_date = request_body.get('end_date', END_DATE)
            output_prefix = request_body.get('output_prefix', OUTPUT_PREFIX)
            filename = request_body.get('filename')
            
            if not filename:
                return {
                    'statusCode': 400,
                    'headers': cors_headers,
                    'body': json.dumps({
                        'status': 'error',
                        'message': 'Filename is required for analysis'
                    })
                }
            
            # Download required files from S3
            s3.download_file(S3_BUCKET, EE_KEY_S3_KEY, EE_KEY_PATH)
            
            # Get user data file
            user_data_key = f"uploads/{filename}"
            s3.download_file(S3_BUCKET, user_data_key, DATA_PATH)
            
            # Initialize Earth Engine
            credentials = ee.ServiceAccountCredentials(SERVICE_ACCOUNT, EE_KEY_PATH)
            ee.Initialize(credentials)
            print('Earth Engine initialized successfully')
            
            # Create output directory
            output_dir = "/tmp/forest_classification"
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            # Process the data
            print(start_date, end_date, DATA_PATH)
            result = process_natural_forest_classification(
                DATA_PATH, 
                start_date, 
                end_date, 
                output_dir
            )
            
            if not result:
                return {
                    'statusCode': 400,
                    'headers': cors_headers,
                    'body': json.dumps({
                        'status': 'error',
                        'message': 'Cloud cover is too much, please try another date range'
                    })
                }
            
            image_file, stats_file, image_date = result
            

            # Calculate center of boundary box for file naming
            minx, miny, maxx, maxy = boundary_box.bounds
            center_lat = round((miny + maxy) / 2, 2)
            center_lon = round((minx + maxx) / 2, 2)
            lat_long = f"{center_lat:+.2f}{center_lon:+.2f}"  # e.g., +40.12-74.01
            
            # Upload results to S3 with new file naming
            s3_image_key = f"{output_prefix}/{image_date}-{lat_long}-natural_forest_classification.png"
            s3_stats_key = f"{output_prefix}/{image_date}-{lat_long}-natural_forest_stats.json"
            
            s3.upload_file(
                image_file, 
                S3_BUCKET, 
                s3_image_key,
                ExtraArgs={'ContentType': 'image/png'}
            )
            s3.upload_file(stats_file, S3_BUCKET, s3_stats_key)
            
            # Generate pre-signed URL for image download
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
            
            # Read stats file
            with open(stats_file, 'r') as f:
                stats_data = json.load(f)
            
            return {
                'statusCode': 200,
                'headers': cors_headers,
                'body': json.dumps({
                    'status': 'success',
                    'image_download_url': image_download_url,
                    'image_date': image_date,
                    'analysis_results': stats_data
                })
            }
        
        else:
            # Unknown operation
            return {
                'statusCode': 400,
                'headers': cors_headers,
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
            'headers': cors_headers,
            'body': json.dumps({
                'status': 'error',
                'message': str(e),
                'trace': error_trace if DEBUG else None
            })
        }

def parse_request_body(event):
    """Parse request body from the event, handling different event formats"""
    if 'body' not in event:
        return {}
    
    body = event['body']
    if body is None:
        return {}
    
    # Handle both string and parsed JSON
    if isinstance(body, str):
        try:
            return json.loads(body)
        except:
            return {}
    else:
        return body

def sanitize_filename(filename):
    """Sanitize the filename to prevent directory traversal and other issues"""
    # Remove path components
    filename = os.path.basename(filename)
    # Replace potentially problematic characters
    safe_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    filename = ''.join(c if c in safe_chars else '_' for c in filename)
    return filename

def generate_presigned_url(operation, params, expiration=3600):
    """Generate a pre-signed URL for S3 operations"""
    try:
        url = s3.generate_presigned_url(
            ClientMethod=operation,
            Params=params,
            ExpiresIn=expiration
        )
        return url
    except Exception as e:
        print(f"Error generating presigned URL: {e}")
        raise
    
def process_natural_forest_classification(json_path, start_date, end_date, output_dir):
    start_time = time.time()
    
    global ENTIRE_EE_BOUNDARY, total_shapely_polygon, boundary_box
    total_shapely_polygon, boundary_box = load_boundary(json_path)
    ENTIRE_EE_BOUNDARY = shapely_to_ee(total_shapely_polygon.wkt)
    
    # Use a more efficient filtering approach
    s2 = ee.ImageCollection('COPERNICUS/S2_HARMONIZED') \
        .filterDate(start_date, end_date) \
        .filterBounds(ENTIRE_EE_BOUNDARY) \
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 35)) \
        .sort('CLOUDY_PIXEL_PERCENTAGE')
    
    s2_size = s2.size().getInfo()
    if s2_size == 0:
        print("No Sentinel-2 images found in the date range.")
        return None
    
    first_image = ee.Image(s2.first())
    cloud_cover = first_image.get('CLOUDY_PIXEL_PERCENTAGE').getInfo()
    print(f"Lowest cloud cover percentage: {cloud_cover}%")
    image_date = ee.Date(first_image.get('system:time_start')).format('YYYY-MM-dd').getInfo()
    
    # Use more efficient filtering and processing for Dynamic World
    dw_collection = ee.ImageCollection('GOOGLE/DYNAMICWORLD/V1') \
        .filterDate(start_date, end_date) \
        .filterBounds(ENTIRE_EE_BOUNDARY)
    
    dw_size = dw_collection.size().getInfo()
    if dw_size == 0:
        print("No Dynamic World images found for the given date range and boundary.")
        return None
    
    # Use mode() for classification to reduce computation
    dw_image = dw_collection.select('label').mode()
    
    # Get protected areas
    protected_areas = get_protected_areas(total_shapely_polygon.wkt, image_date)
    
    # Create enhanced classification
    tree_mask = dw_image.eq(1)
    natural_forest = tree_mask.And(protected_areas)
    enhanced_classification = dw_image.rename('classification').where(natural_forest, 10)
    
    # Calculate statistics
    print("Calculating area statistics...")
    stats_data, stats_file = calculate_area_statistics(
        enhanced_classification, ENTIRE_EE_BOUNDARY, CORRECT_AREA, image_date, output_dir
    )
    
    # Process image with sub-rectangle splitting
    print("Processing image...")
    image_file = process_and_export_image(enhanced_classification, image_date, output_dir)
    
    end_time = time.time()
    print(f"Total execution time: {end_time - start_time:.2f} seconds")
    
    return image_file, stats_file, image_date

# Split the boundary box into smaller sub-rectangles
def split_boundary_box(boundary_box, max_size_km=30):
    minx, miny, maxx, maxy = boundary_box.bounds

    lat_mid = (miny + maxy) / 2
    km_per_deg_lon = 111 * math.cos(math.radians(lat_mid))
    km_per_deg_lat = 111
    width_km = (maxx - minx) * km_per_deg_lon
    height_km = (maxy - miny) * km_per_deg_lat

    if width_km <= max_size_km and height_km <= max_size_km:
        print("Boundary box is small enough, using single rectangle")
        return [boundary_box]

    # Adaptive sizing for larger areas
    if width_km * height_km > 1000:
        max_size_km = min(60, max(30, max_size_km))

    num_x = math.ceil(width_km / max_size_km)
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
            sub_rect = box(sub_minx, sub_miny, sub_maxx, sub_maxy)
            if sub_rect.intersects(total_shapely_polygon):
                sub_rectangles.append(sub_rect)

    return sub_rectangles

# Export a sub-rectangle as PNG
def export_sub_polygon_as_png(image, boundary, max_retries=3):
    colors = {
        0: [65, 155, 223], 1: [57, 125, 73], 2: [136, 176, 83], 3: [122, 135, 198], 4: [228, 150, 53],
        5: [223, 195, 90], 6: [196, 40, 27], 7: [165, 155, 143], 8: [179, 159, 225], 9: [0, 0, 0], 10: [0, 64, 0]
    }
    r_band = ee.Image(0).toByte().rename('red')
    g_band = ee.Image(0).toByte().rename('green')
    b_band = ee.Image(0).toByte().rename('blue')
    for class_value, color in colors.items():
        mask = image.eq(class_value)
        r_band = r_band.where(mask, color[0])
        g_band = g_band.where(mask, color[1])
        b_band = b_band.where(mask, color[2])
    rgb_image = ee.Image.cat([r_band, g_band, b_band]).unmask(0)

    for retry in range(max_retries):
        try:
            url = rgb_image.getDownloadURL({
                'region': boundary,
                'scale': 20,
                'format': 'png',
                'maxPixels': 1e9
            })
            response = requests.get(url, timeout=120)
            if response.status_code == 200:
                return Image.open(io.BytesIO(response.content)).convert("RGB")
            print(f"Failed to download sub-rectangle image: {response.status_code}, retry {retry+1}/{max_retries}")
            time.sleep(2)
        except Exception as e:
            print(f"Error downloading image: {e}, retry {retry+1}/{max_retries}")
            time.sleep(2)

    return None

# Process a single sub-rectangle
def process_sub_polygon(args):
    index, shapely_sub_rect, enhanced_classification, image_date = args

    sub_rect_wkt = shapely_sub_rect.wkt
    ee_sub_rect = shapely_to_ee(sub_rect_wkt)

    forest_classification = enhanced_classification.clip(ee_sub_rect)

    class_png_image = export_sub_polygon_as_png(forest_classification, ee_sub_rect)
    if class_png_image is None:
        return None

    return {
        'index': index,
        'image_date': image_date,
        'png_image': class_png_image,
        'shapely_sub_rect': shapely_sub_rect
    }

# Create a mask for the image based on the boundary
def create_boundary_mask(shapely_polygon, minx, miny, maxx, maxy, width_pixels, height_pixels):
    mask = Image.new('L', (width_pixels, height_pixels), 0)
    draw = ImageDraw.Draw(mask)

    def geo_to_pixel(lon, lat):
        x = int((lon - minx) / (maxx - minx) * width_pixels)
        y = int((maxy - lat) / (maxy - miny) * height_pixels)
        return max(0, min(x, width_pixels - 1)), max(0, min(y, height_pixels - 1))

    if isinstance(shapely_polygon, MultiPolygon):
        for poly in shapely_polygon.geoms:
            coords = list(poly.exterior.coords)
            pixel_coords = [geo_to_pixel(lon, lat) for lon, lat in coords]
            draw.polygon(pixel_coords, fill=255)
    else:
        coords = list(shapely_polygon.exterior.coords)
        pixel_coords = [geo_to_pixel(lon, lat) for lon, lat in coords]
        draw.polygon(pixel_coords, fill=255)

    return mask

# Merge sub-rectangle images and clip to boundary
def merge_images_properly(results, output_dir, image_date):
    results = [r for r in results if r is not None and r.get('png_image') is not None]
    if not results:
        print("No valid sub-rectangle results to merge")
        return None

    minx, miny, maxx, maxy = boundary_box.bounds
    lat_mid = (miny + maxy) / 2
    meters_per_deg_lon = 111000 * math.cos(math.radians(lat_mid))
    meters_per_deg_lat = 111000
    width_m = (maxx - minx) * meters_per_deg_lon
    height_m = (maxy - miny) * meters_per_deg_lat

    # Adaptive scale factor based on area size
    scale_factor = 10
    if width_m * height_m > 1e9:
        scale_factor = 20

    width_pixels = int(width_m / scale_factor)
    height_pixels = int(height_m / scale_factor)
    max_dimension = 5000
    if width_pixels > max_dimension or height_pixels > max_dimension:
        scale_factor = max(width_pixels / max_dimension, height_pixels / max_dimension)
        width_pixels = int(width_pixels / scale_factor)
        height_pixels = int(height_m / scale_factor)

    # Create the merged image
    merged_img = Image.new('RGB', (width_pixels, height_pixels), (0, 0, 0))

    def geo_to_pixel(lon, lat):
        x = int((lon - minx) / (maxx - minx) * width_pixels)
        y = int((maxy - lat) / (maxy - miny) * height_pixels)
        return max(0, min(x, width_pixels - 1)), max(0, min(y, height_pixels - 1))

    # Process and paste each sub-image
    for result in results:
        sub_img = result['png_image']
        sub_rect = result['shapely_sub_rect']
        sub_minx, sub_miny, sub_maxx, sub_maxy = sub_rect.bounds
        x1, y1 = geo_to_pixel(sub_minx, sub_maxy)
        x2, y2 = geo_to_pixel(sub_maxx, sub_miny)
        sub_width = x2 - x1
        sub_height = y2 - y1
        if sub_width <= 0 or sub_height <= 0:
            continue

        resized_sub_img = sub_img.resize((sub_width, sub_height), Image.Resampling.LANCZOS)
        merged_img.paste(resized_sub_img, (x1, y1))

    # Create and apply the boundary mask
    boundary_mask = create_boundary_mask(total_shapely_polygon, minx, miny, maxx, maxy, width_pixels, height_pixels)
    masked_img = Image.composite(merged_img, Image.new('RGB', merged_img.size, (0, 0, 0)), boundary_mask)

    # Create final image with legend
    center_lat = round((miny + maxy) / 2, 2)
    center_lon = round((minx + maxx) / 2, 2)
    lat_long = f"{center_lat:+.2f}{center_lon:+.2f}"
    final_image_file = os.path.join(output_dir, f"{image_date}-{lat_long}-natural_forest_classification.png")
    create_final_image_with_legend(masked_img, final_image_file, image_date)
    return final_image_file

def process_and_export_image(enhanced_classification, image_date, output_dir):
    # Split boundary into sub-rectangles
    sub_rectangles = split_boundary_box(boundary_box, max_size_km=30)
    print(f"Processing {len(sub_rectangles)} sub-rectangles...")

    # Prepare arguments for parallel processing
    process_args = [(i, sub_rect, enhanced_classification, image_date)
                   for i, sub_rect in enumerate(sub_rectangles)]

    # Use parallel processing with ThreadPoolExecutor
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

    if not results:
        print("No results to merge.")
        return None

    # Merge the sub-images
    return merge_images_properly(results, output_dir, image_date)

# Load boundary geometry and boundary box from JSON
def load_boundary(json_path):
    with open(json_path) as f:
        data = json.load(f)

    json_area = data.get('area', 0)
    print(f"Area from JSON file: {json_area:.2f} km²")

    wkt_polygon = data['city_geometry']
    polygon = wkt.loads(wkt_polygon)
    
    bbox_west = data['bbox_west']
    bbox_south = data['bbox_south']
    bbox_east = data['bbox_east']
    bbox_north = data['bbox_north']
    boundary_box = box(bbox_west, bbox_south, bbox_east, bbox_north)

    global CORRECT_AREA
    CORRECT_AREA = json_area

    return polygon, boundary_box

# Convert Shapely polygon to Earth Engine geometry with caching
@lru_cache(maxsize=128)
def shapely_to_ee(poly_wkt):
    # Convert WKT string to shapely polygon
    poly = wkt.loads(poly_wkt)
    
    if isinstance(poly, MultiPolygon):
        multi_coords = [[list(p.exterior.coords)] + [list(r.coords) for r in p.interiors] for p in poly.geoms]
        return ee.Geometry.MultiPolygon(multi_coords)
    else:
        exterior = list(poly.exterior.coords)
        interiors = [list(r.coords) for r in poly.interiors]
        return ee.Geometry.Polygon([exterior] + interiors)

# Get protected areas with caching
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
        print(f"Using WDPA {yyyymm}/polygons")
    except Exception:
        print("Falling back to current WDPA data")
        wdpa = ee.FeatureCollection('WCMC/WDPA/current/polygons')

    protected_areas = wdpa.filterBounds(boundary)
    protected_mask = protected_areas.reduceToImage(
        properties=['WDPAID'],
        reducer=ee.Reducer.firstNonNull()
    ).gt(0).rename('protected')
    return protected_mask.clip(boundary)

# Create the final image with the legend directly added using PIL
def create_final_image_with_legend(map_img, output_file, image_date):
    # Define legend data
    colors = [
        (65, 155, 223),   # Water
        (57, 125, 73),    # Trees
        (136, 176, 83),   # Grass
        (122, 135, 198),  # Flooded Vegetation
        (228, 150, 53),   # Crops
        (223, 195, 90),   # Shrub & Scrub
        (196, 40, 27),    # Built
        (165, 155, 143),  # Bare
        (179, 159, 225),  # Snow & Ice
        (0, 0, 0),        # Cloud
        (0, 64, 0)        # Natural Forest
    ]
    labels = [
        'Water', 'Trees', 'Grass', 'Flooded Vegetation', 'Crops',
        'Shrub & Scrub', 'Built', 'Bare', 'Snow & Ice', 'Cloud', 'Natural Forest'
    ]

    # Calculate dimensions
    map_width, map_height = map_img.size
    legend_width = 200  # Fixed width for the legend
    legend_height = len(labels) * 50 + 20  # 30 pixels per label + padding
    final_width = map_width + legend_width + 20  # 20 pixels padding
    final_height = max(map_height, legend_height) + 60  # 60 pixels for title and padding

    # Create the final image
    final_img = Image.new('RGB', (final_width, final_height), (255, 255, 255))
    final_img.paste(map_img, (10, 50))

    # Draw the title
    draw = ImageDraw.Draw(final_img)
    title = f"Natural Forest Classification ({image_date})"
    draw.text((10, 10), title, fill=(0, 0, 0))

    # Draw the legend directly on the image
    legend_x = map_width + 20
    legend_y = 50
    for i, (color, label) in enumerate(zip(colors, labels)):
        # Draw color rectangle
        rect_y = legend_y + i * 30
        draw.rectangle(
            [legend_x, rect_y, legend_x + 20, rect_y + 20],
            fill=color
        )
        # Draw label text
        draw.text(
            (legend_x + 30, rect_y + 5),
            label,
            fill=(0, 0, 0)
        )

    # Save the final image
    final_img.save(output_file)
    return output_file

# Calculate area statistics for the entire boundary with optimized reducer
def calculate_area_statistics(image, boundary, total_area, image_date, output_dir):
    CLASS_NAMES = [
        'water', 'trees', 'grass', 'flooded_vegetation', 'crops',
        'shrub_and_scrub', 'built', 'bare', 'snow_and_ice', 'cloud',
        'natural_forest'
    ]

    # Use bestEffort for large areas and a higher scale for faster computation
    histogram = image.reduceRegion(
        reducer=ee.Reducer.frequencyHistogram(),
        geometry=boundary,
        scale=10,  # Match original code for better accuracy
        maxPixels=1e13,
        bestEffort=True,
        tileScale=4
    ).get('classification').getInfo() or {}

    class_pixels = {}
    total_pixels = 0

    for class_value, pixel_count in histogram.items():
        class_idx = int(class_value)
        if class_idx < len(CLASS_NAMES):
            class_pixels[CLASS_NAMES[class_idx]] = pixel_count
            total_pixels += pixel_count

    class_areas = {}
    for class_name, pixels in class_pixels.items():
        proportion = pixels / total_pixels if total_pixels > 0 else 0
        class_areas[class_name] = round(proportion * total_area, 5)

    for class_name in CLASS_NAMES:
        if class_name not in class_areas:
            class_areas[class_name] = 0.0

    natural_forest_area = class_areas['natural_forest']
    trees_area = class_areas['trees']
    total_forest_area = natural_forest_area + trees_area

    stats_data = {
        "date": image_date,
        "total_area_km2": round(total_area, 5),
        "forest_area_km2": round(total_forest_area, 5),
        "natural_forest_km2": round(natural_forest_area, 5),
        "natural_forest_percentage": round((natural_forest_area / total_forest_area) * 100, 5) if total_forest_area > 0 else 0,
        "other_trees_km2": round(trees_area, 5),
        "other_trees_percentage": round((trees_area / total_forest_area) * 100, 5) if total_forest_area > 0 else 0,
        "land_cover_classes": {}
    }

    for class_name, area_km2 in sorted(class_areas.items(), key=lambda item: item[1], reverse=True):
        if area_km2 > 0:
            percentage = (area_km2 / total_area) * 100 if total_area > 0 else 0
            stats_data["land_cover_classes"][class_name] = {
                "area_km2": round(area_km2, 5),
                "percentage": round(percentage, 5)
            }

    stats_file = os.path.join(output_dir, f"natural_forest_stats_{image_date}.json")
    with open(stats_file, 'w') as f:
        json.dump(stats_data, f, indent=2)
    return stats_data, stats_file