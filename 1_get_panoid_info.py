import aiohttp
import argparse
import asyncio
import folium
import itertools
import json
import math
import streetview
import time
import traceback
import webbrowser

# Get data about panoids asynchronously
async def get_panoid(lat, lon, session):
    try:
        url = f"https://maps.googleapis.com/maps/api/js/GeoPhotoService.SingleImageSearch?pb=!1m5!1sapiv3!5sUS!11m2!1m1!1b0!2m4!1m2!3d{lat}!4d{lon}!2d50!3m10!2m2!1sen!2sGB!9m1!1e2!11m4!1m3!1e2!2b1!3e2!4m10!1e1!1e2!1e3!1e4!1e8!1e6!5m1!1e2!6m1!1e2&callback=_xdc_._v2mub5"
        async with session.get(url) as resp:
            assert resp.status == 200
            text = await resp.text()
            panoids = streetview.panoids_from_response(text)
            all_panoids.extend(panoids)
    except:
        print(f"[Retrying] Error fetching panoids for ({lat}, {lon}): {e}")
        await asyncio.sleep(10)
        await get_panoid(lat, lon, session)

async def request_loop():
    conn = aiohttp.TCPConnector(limit=100)
    checked_counter = [0]

    async def reporter():
        while checked_counter[0] < len(test_points):
            if checked_counter[0] != 0:
                print(f"[Status] Checked {checked_counter[0]} of {len(test_points)} test points")
            await asyncio.sleep(10)

    async def fetch_wrapper(lat, lon):
        await get_panoid(lat, lon, session)
        checked_counter[0] += 1
    
    async with aiohttp.ClientSession(connector=conn) as session:
        reporter_task = asyncio.create_task(reporter())
        await asyncio.gather(*(fetch_wrapper(lat, lon) for lat, lon in test_points))
        reporter_task.cancel()
        try:
            await reporter_task
        except asyncio.CancelledError:
            pass

# Haversine formula: returns distance for latitude and longitude coordinates
def haversine(p1, p2):
    R = 6373
    lat1 = math.radians(p1[0])
    lat2 = math.radians(p2[0])
    lon1 = math.radians(p1[1])
    lon2 = math.radians(p2[1])

    dlon = lon2 - lon1
    dlat = lat2 - lat1

    a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R*c

async def filter_by_proximity(panoids, min_dist_metres):
    min_dist_km = min_dist_metres / 1000
    filtered = []
    seen_coords = set()
    total = len(panoids)
    start_time = time.time()

    count = 0
    for pan in panoids:
        count += 1
        coord = (round(pan['lat'], 5), round(pan['lon'], 5))
        if coord in seen_coords:
            continue

        if any(haversine((pan['lat'], pan['lon']), (fp['lat'], fp['lon'])) < min_dist_km for fp in filtered):
            continue

        seen_coords.add(coord)
        filtered.append(pan)

        if time.time() - start_time > 10:
            print(f"[Status] Filtered {count} / {total}")
            start_time = time.time()

    return filtered

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Google Street View Panorama Scraper')
    parser.add_argument('--zoom', type=int, default=12, help='Initial zoom level of the map (default: 12)')
    parser.add_argument('--lat', type=float, default=51.7333449, help='Center latitude')
    parser.add_argument('--lon', type=float, default=0.4734951, help='Center longitude')
    parser.add_argument('--radius', type=float, default=2, help='Search radius in km (default: 2)')
    parser.add_argument('--resolution', type=int, default=50, help=(
        'Grid resolution for sampling test points (default: 50). '
        'Higher values generate more test points and increase panorama coverage, '
        'but also increases runtime. '
        'Roughly (resolution + 1)^2 points are tested within the defined radius.'
        )
    )
    parser.add_argument('--prox', type=float, default=20, help='Minimum distance between panoramas in metres (default: 20)')
    parser.add_argument('--ignore_prox', type=bool, default=False, help='Disable proximity filtering')
    parser.add_argument('--show_test_points', type=bool, default=False, help='Show/hide the test points')

    args = parser.parse_args()
    center = (args.lat, args.lon)
    lat_range = args.radius / 70
    lon_range = args.radius / 70

    # Calculate area bounds
    top_left = (center[0] - lat_range, center[1] + lon_range)
    bottom_right = (center[0] + lat_range, center[1] - lon_range)
    lat_steps = top_left[0] - bottom_right[0]
    lon_steps = top_left[1] - bottom_right[1]

    # Generate grid of test points within radius
    test_points = [
        (bottom_right[0] + x * lat_steps / args.resolution, bottom_right[1] + y * lon_steps / args.resolution)
        for x, y in itertools.product(range(args.resolution + 1), repeat=2)
    ]
    test_points = [p for p in test_points if haversine(p, center) <= args.radius]

    # Create map
    M = folium.Map(location=center, tiles='OpenStreetMap', zoom_start=args.zoom)

    # Show lat/lon popups
    M.add_child(folium.LatLngPopup())

    # Mark area
    folium.Circle(
        location = center,
        radius = args.radius*1000,
        color = '#FF000099',
        fill = 'True'
    ).add_to(M)

    # Show/hide test points
    if args.show_test_points:
        for point in test_points:
            folium.Circle(
                location = point,
                radius = 1,
                color = 'red'
            ).add_to(M)

    # Fetch panorama metadata
    print(f"Gathering panoids from {len(test_points)} test points...")
    all_panoids = list()
    asyncio.run(request_loop())
    print(f"Fetched {len(all_panoids)} total panoids")

    # Filter panoids
    if args.ignore_prox:
        print("Skipping proximity filtering...")
        filtered_panoids = {p['panoid']: p for p in all_panoids}.values()
    else:
        print("Applying proximity filtering...")
        filtered_panoids = asyncio.run(filter_by_proximity(all_panoids, args.prox))

    print(f"Final post-filtering panorama count: {len(filtered_panoids)}")

    # Add panoids to map
    for pan in filtered_panoids:
        folium.CircleMarker(
            location = (pan['lat'], pan['lon']),
            radius = 1,
            popup = pan['panoid'],
            color = 'blue',
            fill = True
        ).add_to(M)

    # Save results
    json_file = f'panoids_{len(filtered_panoids)}.json'
    with open(json_file, 'w') as f:
        json.dump(filtered_panoids, f, indent=2)

    # Save map and open it
    file = f'Result_{len(filtered_panoids)}.html'
    print(f"Saved map to {file} and JSON to {json_file}")
    M.save(file)
    webbrowser.open(file)
