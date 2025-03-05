import overpy
import logging
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
from geopy.distance import geodesic
from time import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("hospital_finder.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize Nominatim with rate limiting and increased timeout
geolocator = Nominatim(user_agent="hospital_finder", timeout=10)
geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1)
reverse_geocode = RateLimiter(geolocator.reverse, min_delay_seconds=1)

# Cache for coordinates and reverse geocoding to avoid repeated API calls
coords_cache = {}
reverse_cache = {}

# Semaphore to limit reverse geocoding to 1 request per second
rate_limit_semaphore = threading.Semaphore(1)


# Function to perform reverse geocoding for a single coordinate pair
def fetch_reverse_geocode(coords):
    lat, lon = coords
    key = (lat, lon)
    if key in reverse_cache:
        return key, reverse_cache[key]

    with rate_limit_semaphore:  # Ensures only 1 thread makes a request at a time
        try:
            logger.info(f"Reverse geocoding for ({lat}, {lon})")
            location = reverse_geocode((lat, lon), exactly_one=True)
            address = location.address if location else "Address not found"
            reverse_cache[key] = address
            logger.info(f"Reverse geocoded address: {address}")
            return key, address
        except Exception as e:
            logger.error(f"Reverse geocoding failed for ({lat}, {lon}): {str(e)}")
            address = f"Coordinates: ({lat}, {lon})"
            reverse_cache[key] = address
            return key, address


# Convert OSM nodes to medical facility dictionaries with parallel reverse geocoding
def node_to_medical_facility(nodes, found_in, ref_lat=None, ref_lon=None):
    start_time = time()
    facilities = []
    coords_to_geocode = []

    # First pass: Process nodes and identify those needing reverse geocoding
    logger.info(f"Processing {len(nodes)} nodes locally")
    for node in nodes:
        facility_type = node.tags.get("healthcare", node.tags.get("amenity", "Unknown"))
        address = node.tags.get("addr:full")
        if not address:
            components = [node.tags.get(k) for k in
                          ["addr:housenumber", "addr:street", "addr:city", "addr:state", "addr:postcode"] if
                          node.tags.get(k)]
            address = ", ".join(components) if components else None

        distance = None
        if ref_lat and ref_lon:
            distance = geodesic((ref_lat, ref_lon), (node.lat, node.lon)).kilometers

        facility = {
            "name": node.tags.get("name", "Unknown"),
            "type": facility_type,
            "lat": node.lat,
            "lon": node.lon,
            "address": address,
            "found_in": found_in,
            "distance": distance
        }

        if not address:
            coords_to_geocode.append((node.lat, node.lon))
        facilities.append(facility)

    # Second pass: Parallel reverse geocoding with rate limiting
    if coords_to_geocode:
        logger.info(f"Starting reverse geocoding for {len(coords_to_geocode)} facilities with rate limiting")
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_coords = {executor.submit(fetch_reverse_geocode, coords): coords for coords in coords_to_geocode}
            for future in as_completed(future_to_coords):
                key, address = future.result()
                for facility in facilities:
                    if (facility["lat"], facility["lon"]) == key:
                        facility["address"] = address
                        break

    logger.info(f"Processed {len(facilities)} facilities in {time() - start_time:.2f} seconds")
    return facilities


# Query medical facilities in a named area
def query_hospitals_in_area(api, area_name, parent_area):
    start_time = time()
    logger.info(f"Querying OSM for hospitals in {area_name} within {parent_area}")
    query = f"""
    [out:json][timeout:25];
    area["name"="{parent_area}"]->.parent;
    area["name"="{area_name}"](area.parent)->.area;
    (
      node(area.area)["amenity"~"hospital|clinic|dentist|pharmacy|doctors|veterinary|nursing_home|health_post"];
      node(area.area)["healthcare"~"hospital|clinic|dentist|pharmacy|doctor|veterinarian|nursing_home|health_post"];
    );
    out body;
    """
    try:
        result = api.query(query)
        hospitals = node_to_medical_facility(result.nodes, area_name)
        logger.info(f"Found {len(hospitals)} facilities in {area_name} in {time() - start_time:.2f} seconds")
        return hospitals
    except Exception as e:
        logger.error(f"Query failed for area {area_name}: {str(e)}")
        return []


# Query medical facilities in a bounding box
def query_hospitals_in_bbox(api, lat, lon, delta=0.045):
    start_time = time()
    south, north = lat - delta, lat + delta
    west, east = lon - delta, lon + delta
    logger.info(f"Querying OSM in bounding box ({south},{west},{north},{east})")
    query = f"""
    [out:json][timeout:25];
    (
      node["amenity"~"hospital|clinic|dentist|pharmacy|doctors|veterinary|nursing_home|health_post"]({south},{west},{north},{east});
      node["healthcare"~"hospital|clinic|dentist|pharmacy|doctor|veterinarian|nursing_home|health_post"]({south},{west},{north},{east});
    );
    out body;
    """
    try:
        result = api.query(query)
        hospitals = node_to_medical_facility(result.nodes, "bounding box", lat, lon)
        logger.info(f"Found {len(hospitals)} facilities in bounding box in {time() - start_time:.2f} seconds")
        return hospitals
    except Exception as e:
        logger.error(f"Bounding box query failed: {str(e)}")
        return []


# Query medical facilities within a radius around a point
def query_hospitals_around(api, lat, lon, radius=5000):
    start_time = time()
    logger.info(f"Querying OSM within {radius / 1000} km radius of ({lat}, {lon})")
    query = f"""
    [out:json][timeout:25];
    (
      node(around:{radius},{lat},{lon})["amenity"~"hospital|clinic|dentist|pharmacy|doctors|veterinary|nursing_home|health_post"];
      node(around:{radius},{lat},{lon})["healthcare"~"hospital|clinic|dentist|pharmacy|doctor|veterinarian|nursing_home|health_post"];
    );
    out body;
    """
    try:
        result = api.query(query)
        hospitals = node_to_medical_facility(result.nodes, f"within {radius / 1000} km", lat, lon)
        hospitals.sort(key=lambda h: h["distance"] or float('inf'))
        logger.info(f"Found {len(hospitals)} facilities within {radius / 1000} km in {time() - start_time:.2f} seconds")
        return hospitals
    except Exception as e:
        logger.error(f"Radius query failed for radius {radius}: {str(e)}")
        return []


# Get coordinates using Nominatim
def get_coords(area_name, district, state, country):
    start_time = time()
    full_address = f"{area_name}, {district}, {state}, {country}"
    logger.info(f"Geocoding address: {full_address}")
    if full_address in coords_cache:
        logger.info(f"Retrieved cached coordinates for {full_address}")
        return coords_cache[full_address]
    try:
        location = geocode(full_address)
        if location:
            coords = (location.latitude, location.longitude)
            coords_cache[full_address] = coords
            logger.info(f"Geocoded {full_address} to {coords} in {time() - start_time:.2f} seconds")
            return coords
    except Exception as e:
        logger.error(f"Geocoding failed for {full_address}: {str(e)}")
    return None


# Filter medical facilities by address
def filter_by_address(hospitals, area_name):
    start_time = time()
    logger.info(f"Filtering facilities by address containing {area_name}")
    filtered = [h for h in hospitals if area_name.lower() in h["address"].lower()]
    logger.info(f"Filtered to {len(filtered)} facilities in {time() - start_time:.2f} seconds")
    return filtered


# Main function to find medical facilities with enhanced search
def get_hospitals(country, state, district, area_name):
    start_time = time()
    logger.info(f"Starting hospital search for {area_name}, {district}, {state}, {country}")
    api = overpy.Overpass()

    # Step 1: Try querying the named area directly
    hospitals = query_hospitals_in_area(api, area_name, district)
    if hospitals:
        logger.info(f"Search completed with named area results in {time() - start_time:.2f} seconds")
        return hospitals

    # Step 2: Try geocoding and bounding box
    coords = get_coords(area_name, district, state, country)
    if coords:
        hospitals = query_hospitals_in_bbox(api, coords[0], coords[1])
        if hospitals:
            logger.info(f"Search completed with bounding box results in {time() - start_time:.2f} seconds")
            return hospitals

        # Step 3: If no results, search within increasing radii
        max_radius = 50000  # 50 km
        radius_step = 5000  # 5 km
        current_radius = 5000
        while current_radius <= max_radius:
            hospitals = query_hospitals_around(api, coords[0], coords[1], current_radius)
            if hospitals:
                logger.info(
                    f"Search completed with radius {current_radius / 1000} km results in {time() - start_time:.2f} seconds")
                return hospitals[:10]
            current_radius += radius_step

    # Step 4: Fallback to parent area (district) and filter by address
    parent_hospitals = query_hospitals_in_area(api, district, state)
    filtered = filter_by_address(parent_hospitals, area_name)
    if filtered:
        logger.info(f"Search completed with filtered district results in {time() - start_time:.2f} seconds")
        return filtered

    # Step 5: Return empty list if no facilities found
    logger.warning(f"No hospitals found after {time() - start_time:.2f} seconds")
    return []


# Example usage
if __name__ == "__main__":
    facilities = get_hospitals("Japan", "Tokyo", "Shibuya", "Shibuya")
    for facility in facilities:
        print(f"Name: {facility['name']}, Type: {facility['type']}, Address: {facility['address']}, "
              f"Lat: {facility['lat']}, Lon: {facility['lon']}, Distance: {facility['distance']} km")