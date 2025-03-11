# Medifind - Hospital Finder

### Overview
**Medifind** is a Flask-based web application that helps users locate hospitals and medical facilities based on geographical location. It utilizes OpenStreetMap (OSM) and geolocation services to fetch hospital data for a given area.

### Features
- Search for hospitals by specifying **country, state, district, and area**.
- Retrieves hospitals, clinics, pharmacies, and other healthcare facilities from **OSM Overpass API**.
- **Geocoding and reverse geocoding** support to refine location-based searches.
- **Distance calculation** for facilities relative to the search area.
- **Optimized API requests** with rate-limiting and caching.

### Directory Structure
```
jefino9488-medifind/
├── app.py                  # Main Flask application
├── get_hospitals.py        # Hospital retrieval and geolocation logic
└── templates/
    └── index.html          # Frontend UI for hospital search
```

### Installation & Setup
#### Prerequisites
- Python 3.x
- Pip (Python Package Manager)

#### Install Required Dependencies
```bash
pip install flask overpy geopy
```

### Usage
#### Run the Flask App
```bash
python app.py
```
The server will start at **http://127.0.0.1:5000/**.

#### Search for Hospitals
Visit the homepage and enter:
- **Country**
- **State**
- **District**
- **Area**

Click **Search** to get hospital results.

Alternatively, use the API endpoint:
```
GET /<country>/<state>/<district>/<area>/hospitals
```
Example:
```
GET /Japan/Tokyo/Shibuya/Shibuya/hospitals
```

### API Response Format
```json
{
    "hospitals": [
        {
            "name": "Tokyo General Hospital",
            "type": "hospital",
            "lat": 35.6895,
            "lon": 139.6917,
            "address": "Shibuya, Tokyo, Japan",
            "found_in": "Shibuya",
            "distance": 2.5
        }
    ],
    "message": "Found 1 hospital in Shibuya"
}
```


### Technologies Used
- **Flask** - Web framework
- **Overpass API** - Fetches hospital data from OpenStreetMap
- **Geopy** - Geolocation services (Nominatim, distance calculations)
- **HTML, JavaScript** - Basic frontend interface
