import asyncio
import json
import os
import argparse
import traceback

import aiohttp

import streetview


async def download_tiles_async(tiles, directory, session):
    """ Downloads all the tiles in a Google Street View panorama into a directory. """

    for i, (x, y, fname, url) in enumerate(tiles):
        # Try to download the image file
        url = url.replace("http://", "https://")
        while True:
            try:
                async with session.get(url) as response:
                    content = await response.read()
                    with open(os.path.join(directory, fname), 'wb') as out_file:
                        out_file.write(content)
                    break
            except Exception:
                print(traceback.format_exc())


async def download_panorama(panoid,
                            session=None,
                            tile_directory='tiles',
                            pano_directory='panoramas'):
    """ 
    Downloads a panorama from latitude and longitude
    Heavily IO bound (~98%), ~40s per panorama without using asyncio.
    """
    if not os.path.isdir(tile_directory):
        os.makedirs(tile_directory)
    if not os.path.isdir(pano_directory):
        os.makedirs(pano_directory)

    try:
        x = streetview.tiles_info(panoid['panoid'])
        await download_tiles_async(x, tile_directory, session)
        streetview.stich_tiles(panoid['panoid'],
                               x,
                               tile_directory,
                               pano_directory,
                               point=(panoid['lat'], panoid['lon']))
        streetview.delete_tiles(x, tile_directory)

    except Exception:
        print(f'Failed to create panorama\n{traceback.format_exc()}')


def panoid_created(panoid):
    """ Checks if the panorama was already created """
    file = f"{panoid['lat']}_{panoid['lon']}_{panoid['panoid']}.jpg"
    return os.path.isfile(os.path.join('panoramas', file))


async def download_loop(panoids, pmax):
    """ Main download loop """
    conn = aiohttp.TCPConnector(limit=100)
    async with aiohttp.ClientSession(connector=conn,
                                     auto_decompress=False) as session:
        try:
            await asyncio.gather(*[
                download_panorama(panoid, session=session)
                for panoid in panoids[:pmax] if not panoid_created(panoid)
            ])
        except Exception:
            print(traceback.format_exc())


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description='Download panorama data from Google Street View')
    parser.add_argument('filename',
                    type=str,
                    nargs='?',
                    help='Name of the output file')
    parser.add_argument('--file',
                        type=str,
                        default=None,
                        help='Name of the output file')
    args = parser.parse_args()

    # Determine the filename
    file = args.filename if args.filename else args.file

    if not file:
        print('Please provide the file with panoids info either as a positional argument or using --file')
        exit(1)

    # Load panoids info
    with open(file, 'r') as f:
        panoids = json.load(f)

    print(f"Loaded {len(panoids)} panoids")

    # Download panorama in batches of 100
    for i in range(1, 100):
        print(f'Running the next batch: {(i-1)*100+1} → {i*100}')
        asyncio.run(download_loop(panoids, 100 * i))