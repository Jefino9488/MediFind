from flask import Flask, render_template, jsonify
from get_hospitals import get_hospitals

app = Flask(__name__)

@app.route('/')
def index():
    return render_template("index.html")

@app.route('/<country>/<state>/<district>/<area>/hospitals', methods=['GET'])
def hospitals(country, state, district, area):
    try:
        hospital_data = get_hospitals(country, state, district, area)
        if not hospital_data:
            return jsonify({"message": "No hospitals found in this area or nearby."}), 404
        # Add a message if results are from a broader area
        found_in = hospital_data[0]["found_in"] if hospital_data else area
        response = {
            "hospitals": hospital_data,
            "message": f"Showing {len(hospital_data)} hospitals from {found_in}" if found_in != area else f"Found {len(hospital_data)} hospitals in {area}"
        }
        return jsonify(response)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)