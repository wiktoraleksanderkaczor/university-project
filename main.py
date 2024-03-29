import sys
sys.path.append("./modules")

from config import *
from fileio import create_folder, filename
from pprint import pprint
from multiprocessing import cpu_count
import os
import json
from glob import glob

try:
    LOCATION = \
        """
    CURRENT LOCATION IS (if untrue, exit):
        Address: {}
        Latitude and Longitude: {}, {}
        https://www.google.com/maps/@{},{},17.5z
    """.format(location.address, location.latitude,
            location.longitude, location.latitude,
            location.longitude)
except Exception as e:
    print("LOCATION COULD NOT BE FOUND")
    print(e)
    exit(1)

MENU = \
"""
OPTIONS (Recommended steps ordered will be in [N] format):
	1. Download from Flickr [1]
	2. Fix image by renaming JPEGs to JPG, converting PNGs, and running "jpeginfo".
	3. Ensure minimum resolution, image over blurry threshold and no duplicates in set
	4. Get GPS data, verify, segregate, make a cleared version and save the good data in JSON.
	5. Copy relevant images to "openMVG" folder.
	6. OpenMVG Feature Detection and Matching
	7. OpenMVG Reconstruct model
	8. OpenMVG Georegister Model
	9. OpenMVG Localise unused cleared GPS images, for accuracy checking.
	10. Move everything to "reconstructions" folder 
	11. Merge reconstructions dialog
	-1. EXIT
"""

def handle_choice(choice):
    if choice == 1:
        from download import links_from_flickr, download
        links = links_from_flickr(TOPIC)
        download(links, "intermediate/images/")

    elif choice == 2:
        from images import images_rename
        images_rename("intermediate/images/")

        commands = [
            # Convert PNGs to JPGs.
            """mogrify -format jpg {}*.png;""".format(
                "intermediate/images/"),

            # Remove PNG duplicates
            """rm {}/*.png;""".format("intermediate/images/"),

            # Check for faulty JPGs, if so, remove.
            """jpeginfo -cd {}*.jpg;""".format("intermediate/images/")
        ]
        for cmd in commands:
            os.system(cmd)

    elif choice == 3:
        from images import check_images, get_duplicate_images
        check_images("intermediate/images/", "intermediate/too_small/", "intermediate/too_blurry/",
                     RESOLUTION_THRESHOLD=PIXEL_NUM_THRESHOLD, BLURRINESS_THRESHOLD=BLURRINESS_THRESHOLD)

        close_images = get_duplicate_images(
            "intermediate/images/", "intermediate/duplicates/", threshold=CLOSE_IMAGE_THRESHOLD)
        print("IMAGES CLOSE BY HASH:")
        pprint(close_images)

    elif choice == 4:
        from gps import get_gps
        get_gps("intermediate/images/",
                "intermediate/some_gps/",
                "intermediate/good_gps/",
                "intermediate/bad_gps/",
                location,
                METRES_THR=METRES_RADIUS_THRESHOLD)
        from gps import remove_exif
        remove_exif("intermediate/good_gps/",
                    "intermediate/cleared_gps/")
        remove_exif("intermediate/some_gps/",
                    "intermediate/cleared_some_gps/")

    elif choice == 5:
        from gps import select_and_copy_GPS_images
        select_and_copy_GPS_images("intermediate/images/",
                                   "intermediate/good_gps/",
                                   NUM_GPS_IMAGES,
                                   NUM_LARGEST_IMAGES,
                                   "openMVG/images/")

        localization_images = glob("intermediate/good_gps/*.jpg")
        some_gps_images = glob("intermediate/some_gps/*.jpg")

        with open("logs/images_for_georeferencing.json", "r") as infile:
            used_for_georeferencing = json.load(infile)

        from fileio import copy
        not_used_for_georeferencing = []
        for image in localization_images:
            if image not in used_for_georeferencing:
                copy("intermediate/cleared_gps/"+filename(image), "openMVG/localization_images/" + filename(image))
                not_used_for_georeferencing.append(image)

        for image in some_gps_images:
            copy("intermediate/cleared_some_gps/"+filename(image), "openMVG/some_gps_localization/" + filename(image))
        
        with open("logs/not_used_for_georeferencing.json", "w+") as outfile:
            json.dump(not_used_for_georeferencing, outfile, indent=4)

    elif choice == 6:
        commands = [
            """
			openMVG_main_SfMInit_ImageListing \
				-i openMVG/images \
				-d sensor_database.txt \
				-o openMVG/init \
                | tee logs/image_listing.txt
			""",

            """
			openMVG_main_ComputeFeatures \
				-i openMVG/init/sfm_data.json \
				-o openMVG/data \
				--describerMethod SIFT \
				--describerPreset {} \
                --numThreads {}
			""".format(DESCRIBER_PRESET, cpu_count()),

            """
			openMVG_main_ComputeMatches \
				-i openMVG/init/sfm_data.json \
				-o openMVG/data/ \
                --guided_matching 1 \
                --force 1 \
                | tee logs/matching.txt
			"""
        ]
        for cmd in commands:
            os.system(cmd)

    elif choice == 7:
        cmd = \
        """
        openMVG_main_IncrementalSfM \
            -i openMVG/init/sfm_data.json \
            -m openMVG/data \
            -o openMVG/output \
            --prior_usage 0
        """

        os.system(cmd)

    elif choice == 8:
        #from sfm_data import remove_images_from_reconstruction
        cmd = \
        """
        openMVG_main_ConvertSfM_DataFormat \
            -i openMVG/output/sfm_data.bin \
            -o openMVG/output/sfm_data.json
        """
        
        os.system(cmd)

        LMeds_usage = ""
        while LMeds_usage not in ["y", "n"]:
            LMeds_usage = input("Use of the OpenMVG LMeds model for georegistration [y/n]? ")

        if LMeds_usage == "y":
            LMeds_usage = "0"
        else:
            LMeds_usage = "1"

        commands = [
            """
            openMVG_main_ConvertSfM_DataFormat \
				-i openMVG/output/sfm_data.json \
				-o openMVG/output/sfm_data_modified.bin
            """,

            """
            openMVG_main_geodesy_registration_to_gps_position \
				-i openMVG/output/sfm_data_modified.bin \
				-o openMVG/output/sfm_data_geo.bin \
                -m {} \
                | tee logs/georegistration.txt
            """.format(LMeds_usage),

            """
            openMVG_main_ConvertSfM_DataFormat \
				-i openMVG/output/sfm_data_geo.bin \
				-o openMVG/output/sfm_data_geo.json
            """,

            """
            openMVG_main_ConvertSfM_DataFormat \
				-i openMVG/output/sfm_data_geo.bin \
				-o openMVG/output/sfm_data_geo_cloudcompare_viewable.ply
            """
        ]
        for cmd in commands:
            os.system(cmd)

    elif choice == 9:
        commands = [
        """
		openMVG_main_SfM_Localization \
			-i openMVG/output/sfm_data_geo.bin \
			--match_dir openMVG/data \
			--out_dir openMVG/localization_output/ \
			--query_image_dir openMVG/localization_images/ \
			--numThreads {}
		""".format(cpu_count()),

        """
		openMVG_main_SfM_Localization \
			-i openMVG/output/sfm_data_geo.bin \
			--match_dir openMVG/data \
			--out_dir openMVG/some_gps_localization_output/ \
			--query_image_dir openMVG/some_gps_localization/ \
			--numThreads {}
		""".format(cpu_count())
        ]

        for cmd in commands:
            os.system(cmd)

        from gps import export_gps_to_file, get_accuracy, convert_to_kml

        export_gps_to_file(georeference="openMVG/output/sfm_data_geo.json")

        # Accurate GPS images
        export_gps_to_file(
            georeference="openMVG/localization_output/sfm_data_expanded.json")
        get_accuracy("intermediate/gps_data_from_images.json",
                    "openMVG/sfm_data_geo_positions.json",
                    "openMVG/sfm_data_expanded_positions.json",
                    output="openMVG/localised_accuracy.json")

        convert_to_kml(georeference="openMVG/sfm_data_expanded_positions.json", gps_data="openMVG/localised_accuracy.json")

        # Somewhat accurate GPS images
        export_gps_to_file(georeference="openMVG/some_gps_localization_output/sfm_data_expanded.json", 
                            output="openMVG/some_gps_localization_output/")

        get_accuracy("intermediate/some_gps_data_from_images.json",
                    "openMVG/sfm_data_geo_positions.json",
                    "openMVG/some_gps_localization_output/sfm_data_expanded_positions.json",
                    output="openMVG/some_gps_localised_accuracy.json")
        
        convert_to_kml(georeference="openMVG/some_gps_localization_output/sfm_data_expanded_positions.json", output="openMVG/some_gps_positions.kml", gps_data="openMVG/some_gps_localised_accuracy.json")

    elif choice == 10:
        from fileio import move, copy
        create_folder("reconstructions/" + GEO_TOPIC)
        move("openMVG", "reconstructions/" + GEO_TOPIC + "/")
        move("intermediate", "reconstructions/" + GEO_TOPIC + "/")
        move("logs", "reconstructions/"+ GEO_TOPIC + "/")
        copy("./config.py", "reconstructions/" + GEO_TOPIC + "/config.py")

    elif choice == 11:
        from sfm_data import merge_reconstructions
        merge_reconstructions()

    elif choice == -1:
        exit(0)


def main(execute=None):
    if not execute:
        print(LOCATION)
        while True:
            try:
                choice = int(input(MENU))
            except:
                choice = 0
            handle_choice(choice)
    else:
        for choice in execute:
            handle_choice(choice)


if __name__ == "__main__":
    main()
