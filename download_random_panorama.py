import aiohttp
import argparse
import asyncio
import json
import os
import random
import streetview

json_file = '/storage/emulated/0/Download/panoids.json'
download_folder = '/storage/emulated/0/Download/'

with open(json_file, 'r') as file:
    panoids = json.load(file)

random_panoid = random.choice(panoids)

script_dir = os.path.dirname(os.path.realpath(__file__))
tile_directory = os.path.join(script_dir, 'tiles')

os.makedirs(tile_directory, exist_ok=True)

async def download_tiles_async(tiles, session):
    for i, (x, y, fname, url) in enumerate(tiles):
        url = url.replace("http://", "https://")
        while True:
            try:
                async with session.get(url) as response:
                    content = await response.read()
                    with open(os.path.join(tile_directory, fname), 'wb') as out_file:
                        out_file.write(content)
                    break
            except Exception as e:
                print(f"Error downloading tile {fname}: {e}")

async def download_panorama(panoid):
    try:
        tiles = streetview.tiles_info(panoid['panoid'])
        async with aiohttp.ClientSession() as session:
            await download_tiles_async(tiles, session)
        streetview.stich_tiles(panoid['panoid'], tiles, tile_directory, '/storage/emulated/0/DCIM/Downloads', point=(panoid['lat'], panoid['lon']))
        streetview.delete_tiles(tiles, tile_directory)
        print(f"Successfully downloaded and stitched panorama for {panoid['panoid']}.")
    except Exception as e:
        print(f"Failed to download or stitch panorama for {panoid['panoid']}: {e}")

asyncio.run(download_panorama(random_panoid))
