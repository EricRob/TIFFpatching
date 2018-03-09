#!/user/bin/env python3 -tt
"""
Module documentation.
"""

# Imports
import sys
import os
import csv
import pdb
import numpy as np
from skimage import io
from scipy.ndimage import measurements
from skimage.transform import rescale
from math import floor
from numpy.lib.stride_tricks import as_strided
from termcolor import cprint
import numbers

# Global variables

# Class declarations
class OriginalPatchConfig(object):
	image_data_folder_path = "/home/wanglab/Desktop/recurrence_seq_lstm/image_data" # Location of image to be split into patches
	patch_size = 500 # Pixel length and width of each patch square
	tile_size = patch_size * 5
	edge_overlap = 75 # Amount of overlap between patches within a sample
	sample_size = 100 # Final size of patch (usually 100)
	patch_keep_percentage = 75 # Percentage of patch that must be data (i.e. non-background)
	tile_keep_percentage = 35 # Percentage of tile that must contain cell data (i.e. non-background)
	maximum_std_dev = 1.5 * patch_size # Std dev size for a tile with 100% density
	maximum_seq_per_tile = 3 # Round number of sequences to the nearest integer
	image_height = sample_size
	image_width = sample_size
	image_depth = 3
	num_steps = 20

# Function declarations
def extract_tiles(arr, tile_size, edge_overlap):
	arr_ndim = arr.ndim

	tile_shape = (tile_size,tile_size)
	extraction_step = tile_size

	# Assure all objects are tuples of the same shape
	if isinstance(tile_shape, numbers.Number):
	    tile_shape = tuple([tile_shape] * arr_ndim)
	if isinstance(extraction_step, numbers.Number):
	    extraction_step = tuple([extraction_step] * arr_ndim)

	# consistent stride values necessary for arrays of indeterminate size and shape
	tile_strides = arr.strides

	slices = [slice(None, None, st) for st in extraction_step]
	indexing_strides = arr[slices].strides

	tile_indices_shape = ((np.array(arr.shape) - np.array(tile_shape)) //
	                       np.array(extraction_step)) + 1

	shape = tuple(list(tile_indices_shape) + list(tile_shape))
	strides = tuple(list(indexing_strides) + list(tile_strides))

	# Create views into the array with given shape and stride
	tiles = as_strided(arr, shape=shape, strides=strides)


	bottom_edge = bottom_edge_tiles(arr, tile_size, edge_overlap)
	right_edge = right_edge_tiles(arr, tile_size, edge_overlap)

	tiles = adjust_tile_grid_edges(tiles, arr.shape, tile_size, edge_overlap)

	return tiles, bottom_edge, right_edge

def adjust_tile_grid_edges(tiles, shape, tile_size, edge_overlap):
	if shape[0] / tile_size % 1 < (edge_overlap / 100):
		tiles = tiles[:(tiles.shape[0]-1), :, :, :]
	if shape[1] / tile_size % 1 < (edge_overlap / 100):
		tiles = tiles[:,:(tiles.shape[1]-1), :, :]
	return tiles

def bottom_edge_tiles(image, tile_size, edge_overlap):
	if image.shape[0] / tile_size % 1 < (edge_overlap / 100):
		bottom_edge_y_value = (image.shape[0] // tile_size - 1) * tile_size

		bottom_mask_edge = image[bottom_edge_y_value:,:]
		bottom_edge_columns = bottom_mask_edge.shape[1] // tile_size
		bottom_edge = np.zeros((1, bottom_edge_columns, bottom_mask_edge.shape[0], tile_size))
		
		for column in np.arange(bottom_edge.shape[1]):
			column_pixel = column*tile_size
			bottom_edge[0,column,:,:] = image[bottom_edge_y_value:,column_pixel:(column_pixel + tile_size)]
	else:
		bottom_edge_y_value = (image.shape[0] // tile_size) * tile_size
		bottom_mask_edge = image[bottom_edge_y_value:,:]
		bottom_edge_columns = bottom_mask_edge.shape[1] // tile_size
		bottom_edge = np.zeros((1, bottom_edge_columns, image.shape[0] - bottom_edge_y_value, tile_size))
		for column in np.arange(bottom_edge.shape[1]):
			column_pixel = column * tile_size
			bottom_edge[0,column,:,:] = image[bottom_edge_y_value:, column_pixel:(column_pixel + tile_size)]

	return bottom_edge

def right_edge_tiles(image, tile_size, edge_overlap):
	if image.shape[1] / tile_size % 1 < (edge_overlap / 100):
		right_edge_x_value = (image.shape[1] // tile_size - 1) * tile_size
		right_mask_edge = image[:,right_edge_x_value:]
		right_edge_rows = right_mask_edge.shape[0] // tile_size
		right_edge = np.zeros((right_edge_rows, 1, tile_size, right_mask_edge.shape[1]))
		
		for row in np.arange(right_edge.shape[0]):
			row_pixel  = row * tile_size
			right_edge[row,0,:,:] = image[row_pixel:(row_pixel + tile_size),right_edge_x_value:]
	else:
		right_edge_x_value = (image.shape[1] // tile_size) * tile_size
		right_mask_edge = image[right_edge_x_value:, :]
		right_edge_rows = right_mask_edge.shape[0] // tile_size
		right_edge = np.zeros((right_edge_rows, 1, tile_size, image.shape[1] - right_edge_x_value))

		for row in np.arange(right_edge.shape[0]):
			row_pixel = row * tile_size
			right_edge[row,0,:,:] = image[row_pixel:(row_pixel + tile_size), right_edge_x_value:]

	return right_edge

def threshold_tiles(tile_grid, keep_percentage):
	keep_list = []
	keep_threshold = tile_grid.shape[2] * tile_grid.shape[3] * (1 - keep_percentage / 100)
	
	for row in np.arange(tile_grid.shape[0]):
		for col in np.arange(tile_grid.shape[1]):
			tile = tile_grid[row, col, :, :]
			tile_sum = np.sum(tile)
			if tile_sum <= keep_threshold:
				keep_list = keep_list + [(row, col)]
	
	return keep_list

def adjust_bottom_list(bottom_list, add):
	adjusted_list = []
	for tile in bottom_list:
		adjusted_list = adjusted_list + [(tile[0] + add, tile[1])]
	return adjusted_list

def adjust_right_list(right_list, add):
	adjusted_list = []
	for tile in right_list:
		adjusted_list = adjusted_list + [(tile[0], tile[1] + add)]
	return adjusted_list

def tile_density(tile):
	tile_pixels = tile.shape[0]*tile.shape[1]
	tile_sum = np.sum(tile)
	return 1 - tile_sum / tile_pixels

def calculate_main_tile_masses(grid, keep_list):
	centroids = dict()
	for row in np.arange(grid.shape[0]):
		for col in np.arange(grid.shape[1]):
			if (row,col) in keep_list:
				centroids[(row,col)] = dict()
				centroids[(row,col)]["density"] = tile_density(grid[row,col,:,:])
				centroids[(row,col)]["centroid"] = measurements.center_of_mass(grid[row,col,:,:])
	return centroids

def calculate_right_tile_masses(grid, keep_list):
	centroids = dict()
	if len(keep_list) == 0:
		return
	col = keep_list[0][1]
	for row in np.arange(grid.shape[0]):
		if (row,col) in keep_list:
			centroids[(row,col)] = dict()
			centroids[(row,col)]["density"] = tile_density(grid[row,0,:,:])
			centroids[(row,col)]["centroid"] = measurements.center_of_mass(grid[row,0,:,:])
	return centroids

def calculate_bottom_tile_masses(grid, keep_list):
	centroids = dict()
	if len(keep_list) == 0:
		return
	row = keep_list[0][0]
	for col in np.arange(grid.shape[1]):
		if (row,col) in keep_list:
			centroids[(row,col)] = dict()
			centroids[(row,col)]["density"] = tile_density(grid[0,col,:,:])
			centroids[(row,col)]["centroid"] = measurements.center_of_mass(grid[0,col,:,:])
	return centroids

def sample_from_distribution(mask, tile_info, config):
	keep_threshold = config.patch_size**2 * (1 - config.patch_keep_percentage/100)
	for tile in tile_info:
		std_dev = config.maximum_std_dev * tile_info[tile]["density"]
		
		sequence_count = int(round(tile_info[tile]["density"] * config.maximum_seq_per_tile))
		samples = sequence_count * config.num_steps
		tile_info[tile]["coords"] = []
		while len(tile_info[tile]["coords"]) < samples:
			x = int(round(np.random.normal(tile_info[tile]["centroid"][1], std_dev) + tile[1] * config.tile_size))
			y = int(round(np.random.normal(tile_info[tile]["centroid"][0], std_dev) + tile[0] * config.tile_size))
			patch = mask[y:(y+config.patch_size), x:(x+config.patch_size)]
			if np.sum(patch) <= keep_threshold:	
				tile_info[tile]["coords"] = tile_info[tile]["coords"] + [(y,x)]

def split_and_combine_patch_lists(tile_dict, bottom_dict, right_dict, num_steps):
	sequences = []
	sequences = append_patch_lists(sequences, tile_dict, num_steps)
	sequences = append_patch_lists(sequences, bottom_dict, num_steps)
	sequences = append_patch_lists(sequences, right_dict, num_steps)
	return sequences

def append_patch_lists(patch_list, region_dict, num_steps):
	for tile in region_dict:
		coords_list = region_dict[tile]['coords']
		for n in np.arange(len(coords_list) // num_steps):
			patch_list = patch_list + [coords_list[(n*num_steps):((n+1)*num_steps)]]
	return patch_list

def generate_sequences(mask_filename, config):
	tile_size = config.tile_size
	mask = io.imread(mask_filename)
	mask = mask[:,:,0]
	mask[mask > 0] = 1
	cprint("Extracting tiles...", 'green', 'on_white')
	tile_grid, bottom_edge, right_edge = extract_tiles(mask, tile_size, config.edge_overlap)

	cprint("Thresholding tiles...", 'green', 'on_white')
	keep_tile_grid_list = threshold_tiles(tile_grid, config.tile_keep_percentage)

	keep_bottom_edge_list = threshold_tiles(bottom_edge, config.tile_keep_percentage)
	if mask.shape[0] / tile_size % 1 < (config.edge_overlap / 100):
		keep_bottom_edge_list = adjust_bottom_list(keep_bottom_edge_list, tile_grid.shape[0] + 1)
	else:
		keep_bottom_edge_list = adjust_bottom_list(keep_bottom_edge_list, tile_grid.shape[0])

	keep_right_edge_list = threshold_tiles(right_edge, config.tile_keep_percentage)
	if mask.shape[1] / tile_size % 1 < (config.edge_overlap / 100):
		keep_right_edge_list = adjust_right_list(keep_right_edge_list, tile_grid.shape[1] + 1)
	else:
		keep_right_edge_list = adjust_right_list(keep_right_edge_list, tile_grid.shape[1])

	cprint("Calculating centroids...", 'green', 'on_white')
	tile_centroids = calculate_main_tile_masses(tile_grid, keep_tile_grid_list)
	bottom_centroids = calculate_bottom_tile_masses(bottom_edge, keep_bottom_edge_list)
	right_centroids = calculate_right_tile_masses(right_edge, keep_right_edge_list)

	cprint("Sampling around centroids...", 'green', 'on_white')
	sample_from_distribution(mask, tile_centroids, config)
	sample_from_distribution(mask, bottom_centroids, config)
	sample_from_distribution(mask, right_centroids, config)

	cprint("Listing sequences...", 'green', 'on_white')
	sequences = split_and_combine_patch_lists(tile_centroids, bottom_centroids, right_centroids, config.num_steps)

	return sequences

def write_image_bin(image_bin, image_name, subject_ID, sequences, config):
	image_path = os.path.join(config.image_data_folder_path, 'original_images', image_name)
	image = io.imread(image_path)
	# Data saved to binary files as [subject ID][image name][coordinates][sequence data]
	ID_byte_string = str.encode(subject_ID)
	image_name_byte_string = str.encode("{:<100}".format(image_name[:-4])) #padded to 100 characters
	for sequence in sequences:
		coord_byte_string = byte_string_from_coord_array(sequence, config.num_steps)
		image_bin.write(ID_byte_string)
		image_bin.write(image_name_byte_string)
		image_bin.write(coord_byte_string)
		for y,x in sequence:
			patch = image[y:(y+config.patch_size),x:(x+config.patch_size),:]
			# Need to verify this downscaling method
			patch_downscaled = rescale(patch, (100,100))
			print(patch_downscaled.shape)
			image_bin.write(patch_downscaled)


def byte_string_from_coord_array(coord_array, num_steps):
	coord_string = ""
	for y in np.arange(num_steps):
		for x in np.arange(2):
			coord = "{:<6}".format(coord_array[y][x])
			coord_string = coord_string + coord
	return str.encode(coord_string)

def get_config():
	return OriginalPatchConfig()

def main():
	config = get_config()
	image_to_ID_csv_file = open(os.path.join(config.image_data_folder_path,"image_to_patient_ID.csv"),"r")
	reader = csv.reader(image_to_ID_csv_file, delimiter=",")
	image_to_ID_dict = dict()
	for line in reader:
		image_to_ID_dict[line[0]] = line[1]
	os.makedirs(os.path.join(config.image_data_folder_path,'gaussian_patches'), exist_ok=True)
	mask_path = os.path.join(config.image_data_folder_path, "masks")
	mask_list = [os.path.join(config.image_data_folder_path, mask_path, f) for f in os.listdir(mask_path) if os.path.isfile(os.path.join(mask_path, f))]
	for mask in mask_list:
		image_name = mask.split('/')[-1][5:]
		cprint("*-._.-*-._.*" + image_name + "*-._.-*-._.-*", 'white', 'on_green')
		sequences = generate_sequences(mask, config)
		image_path = os.path.join(config.image_data_folder_path, 'original_images', image_name)
		gauss_bin_path = os.path.join(config.image_data_folder_path,'gaussian_patches',image_name.split('.')[0] + '.bin')
		image_bin = open(gauss_bin_path, 'wb+')
		cprint("Writing binary file...", 'green', 'on_white')
		write_image_bin(image_bin, image_name, image_to_ID_dict[image_name], sequences, config)
		image_bin.close()
		pdb.set_trace()

# Main body
if __name__ == '__main__':
	main()