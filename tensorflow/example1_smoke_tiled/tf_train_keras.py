#******************************************************************************
#
# MantaFlow fluid solver framework
# Copyright 2017 Daniel Hook, Nils Thuerey
#
# This program is free software, distributed under the terms of the
# GNU General Public License (GPL) 
# http://www.gnu.org/licenses
#
# Manta & tensor flow example with tiles using Keras
#
#******************************************************************************

import time
import os
import shutil
import sys
import math

import tensorflow as tf
import numpy as np

# load manta tools
sys.path.append("../tools")
import tilecreator as tiCr
import uniio
import paramhelpers as ph
from convautoenc import ConvolutionalAutoEncoder

import keras
#import tf.keras as keras  # TODO, for v1.2 

# path to sim data, trained models and output are also saved here
basePath = '../data/'

# main mode switch:
outputOnly = True  # apply model, or run full training?

simSizeLow   = 64
tileSizeLow  = 16
upRes        = 4

# dont use for training! for applying model, add overlap here if necessary (i.e., cropOverlap>0) 
# note:  cropTileSizeLow + (cropOverlap * 2) = tileSizeLow
cropOverlap     = 0
cropTileSizeLow = tileSizeLow - 2*cropOverlap

emptyTileValue  = 0.01
learningRate    = 0.00005
trainingEpochs  = 10000 # for large values, stop manualy with ctrl-c...
dropout         = 0.9   # slight...
batchSize       = 100
testInterval    = 200
saveInterval    = 10
#saveInterval    = 50 # increase for long runs...
fromSim = toSim = -1
keepAll         = False
numTests        = 10      # evaluate on 10 data points from test data
randSeed        = 1
fileFormat      = "npz"

# run this many iterations per keras fit call
kerasChunk = 100

# optional, add velocity as additional channels to input?
useVelocities   = 0


# ---------------------------------------------

# load an existing model when load_ values > -1
# when training , manually abort when it's good enough
# then enter test_XXXX id below to load

loadModelTest = -1
loadModelNo   = -1
testPathStartNo = 1

# command line params
outputOnly      = int(ph.getParam( "out",             outputOnly ))>0
trainingEpochs  = int(ph.getParam( "trainingEpochs",  trainingEpochs ))
loadModelTest   = int(ph.getParam( "loadModelTest",   loadModelTest))
loadModelNo     = int(ph.getParam( "loadModelNo",     loadModelNo))
basePath        =     ph.getParam( "basePath",        basePath        )
useVelocities   = int(ph.getParam( "useVelocities",   useVelocities  ))
testPathStartNo = int(ph.getParam( "testPathStartNo", testPathStartNo  ))
fromSim         = int(ph.getParam( "fromSim",         fromSim  )) # range of sim data to use
toSim           = int(ph.getParam( "toSim",           toSim  ))
alwaysSave      = int(ph.getParam( "alwaysSave",      False  )) # by default, only save when cost is lower, can be turned off here
randSeed        = int(ph.getParam( "randSeed",        randSeed )) 
simSizeLow      = int(ph.getParam( "simSizeLow",      simSizeLow )) 
upRes           = int(ph.getParam( "upRes",           upRes ))
#fileFormat     =     ph.getParam( "fileFormat",      fileFormat) # fixed to npz here
ph.checkUnusedParams()

# initialize
simSizeHigh  = simSizeLow   * upRes
tileSizeHigh = tileSizeLow  * upRes
if outputOnly: # dont discard
	emptyTileValue = -1.

if toSim==-1:
	toSim = fromSim
tiCr.setBasePath(basePath)

np.random.seed(randSeed)
tf.set_random_seed(randSeed)

if not outputOnly:
	# run train!
	loadModelTest = -1
	if fromSim==-1:
		fromSim = toSim  = 1000 # short default, use single sim

	if cropOverlap>0:
		print("Error - dont use cropOverlap != 0 for training...")
		exit(1)

else:
	keepAll = True

# ---------------------------------------------

# create output dir
def next_test_path(folder_no = 1):
	test_path_addition = 'test_%04d/' % folder_no
	while os.path.exists(basePath + test_path_addition):
		folder_no += 1
		test_path_addition = 'test_%04d/' % folder_no 
		test_folder_no = folder_no
	test_path = basePath + test_path_addition
	print("Using test dir '%s'" % test_path)
	os.makedirs(test_path)
	return (test_path, folder_no)

# create model loading path
if not loadModelTest == -1:
	if not os.path.exists(basePath + 'test_%04d/' % loadModelTest):
		print('ERROR: Test to load does not exist.')
	# search for newest model if no loadModelNo is given
	if loadModelNo == -1:
		for currModel in range(0, 999):
			if os.path.isfile(basePath + 'test_%04d/model_%04d.kkpt' % (loadModelTest, currModel)):
				loadModelNo = currModel
		if loadModelNo == -1:
			print('ERROR: Model with id below 200 does not exist. Please specify model id as "loadModelNo".')
			exit()
		# print('Latest model: %d.' % loadModelNo)

	load_path = basePath + 'test_%04d/model_%04d.kkpt' % (loadModelTest, loadModelNo)

(test_path,test_folder_no) = next_test_path(testPathStartNo)
if not outputOnly: uniio.backupFile(__file__, test_path)

# custom Logger to write Log to file
class Logger(object):
	def __init__(self):
		self.terminal = sys.stdout
		self.log = open(test_path + "logfile.log", "a")

	def write(self, message):
		self.terminal.write(message)
		self.log.write(message)

	def flush(self): 
		# to avoid errormsg, " AttributeError: 'Logger' object has no attribute 'flush' "
		pass
sys.stdout = Logger()

print("Call: " + str(" ".join(sys.argv) ) )

# print Variables to log
def print_variables():
	print('\nUsing variables:')
	print('fromSim: {}'.format(fromSim))
	print('toSim: {}'.format(toSim))
	print('simSizeLow: {}'.format(simSizeLow))
	print('tileSizeLow: {}'.format(tileSizeLow))
	print('cropOverlap: {}'.format(cropOverlap))
	print('cropTileSizeLow: {}'.format(cropTileSizeLow))
	print('upRes: {}'.format(upRes))
	print('emptyTileValue: {}'.format(emptyTileValue))
	print('learningRate: {}'.format(learningRate))
	print('trainingEpochs: {}'.format(trainingEpochs))
	print('dropout: {}'.format(dropout))
	print('batchSize: {}'.format(batchSize))
	print('\n')

print_variables()

n_input  = tileSizeLow  ** 2 
n_output = tileSizeHigh ** 2
n_inputChannels = 1

if useVelocities:
	n_inputChannels = 4
n_input *= n_inputChannels

clFMs = int(8 / n_inputChannels)
#print( "inputs " + format(len( tiCr.tile_data['inputs_train']) ))

model = keras.models.Sequential()
model.add( keras.layers.Conv2D(clFMs/2, (2,2), activation='relu', strides=(2,2), input_shape=(16,16,n_inputChannels), padding='same' ) )

model.add( keras.layers.Conv2D(clFMs  , (2,2), activation='relu', strides=(2,2), padding='same' ) )
model.add( keras.layers.BatchNormalization() )  
model.add( keras.layers.Flatten() ) # not really needed

model.add( keras.layers.Dense(4*4*clFMs, activation='relu') )
model.add( keras.layers.BatchNormalization() )  
model.add( keras.layers.Dropout(0.25) )  
model.add( keras.layers.Reshape( (4,4,clFMs) ) ) # for flatten, not really needed

model.add( keras.layers.convolutional.Conv2DTranspose(clFMs,   (2,2), activation='relu', strides=(2,2), padding='same' ) )
model.add( keras.layers.convolutional.Conv2DTranspose(clFMs/2, (2,2), activation='relu', strides=(2,2), padding='same' ) )
model.add( keras.layers.convolutional.Conv2DTranspose(clFMs/4, (2,2), activation='relu', strides=(2,2), padding='same' ) )
model.add( keras.layers.convolutional.Conv2DTranspose(1,       (4,4), activation='relu', strides=(2,2), padding='same' ) )

model.compile( loss='mse', optimizer='adam') #, metrics=['accuracy'] )

# load test data, note no split into train & test/validation set necessary here, done by keras during fit
tiCr.loadTestDataNpz(fromSim, toSim, emptyTileValue, cropTileSizeLow, cropOverlap, 1.0, 0.0, load_vel=useVelocities, low_res_size=simSizeLow, upres=upRes, keepAll=keepAll)

# manually reshape data
#print( format( tiCr.tile_data['inputs_train'].shape) + " " + format( tiCr.tile_data['outputs_train'].shape) ) # 16x16, 64x64
dataSize = tiCr.tile_data['outputs_train'].shape[0]
tiCr.tile_data['inputs_train']  = np.reshape( tiCr.tile_data['inputs_train'],  [dataSize,tileSizeLow,tileSizeLow,  n_inputChannels] )
tiCr.tile_data['outputs_train'] = np.reshape( tiCr.tile_data['outputs_train'], [dataSize,tileSizeHigh,tileSizeHigh,1 ] )

if not outputOnly:
	startTime = time.time()
	if 1:
		lastCost   = 1e10
		lastSave   = 1
		save_no    = 0
		trainingEpochs = int(trainingEpochs/kerasChunk)
		for epoch in range(trainingEpochs):
			batch_xs, batch_ys = tiCr.selectRandomTiles(batchSize*kerasChunk) 
			batch_xs  = np.reshape( batch_xs,  [batchSize*kerasChunk,tileSizeLow,tileSizeLow,  n_inputChannels] )
			batch_ys  = np.reshape( batch_ys,  [batchSize*kerasChunk,tileSizeHigh,tileSizeHigh,  1] )
			#model.fit( tiCr.tile_data['inputs_train'], tiCr.tile_data['outputs_train'], batch_size=batchSize, epochs=1 )
			hist = model.fit( batch_xs, batch_ys, batch_size=batchSize, epochs=1, validation_split=0.05 )

			#_, cost, summary = sess.run([optimizer, costFunc, lossTrain], feed_dict={x: batch_xs, y_true: batch_ys, keep_prob: dropout})
			cost = lastCost - 1.0 # NT_DEBUG fix
			# NT_DEBUG print(format(hist))

			# save model
			doSave = False
			if ((cost < lastCost) or alwaysSave) and (lastSave >= saveInterval): doSave = True
			if epoch == (trainingEpochs-1): doSave = True # save last state

			if doSave:
				model.save_weights(test_path + 'model_%04d.kkpt' % save_no)
				print('Saved Model with cost %f.' % cost)
				save_no += 1
				lastSave = 1
				lastCost = cost
			else:
				lastSave += 1
			print('\nEpoch {:04d}/{:04d} - Cost= {:.9f} - Cost_test= {:.9f}'.format((epoch + 1), trainingEpochs, 0., 0.))

	print('\n*****TRAINING %d FINISHED*****' % test_folder_no)
	training_duration = (time.time() - startTime) / 60.0
	#print('Training needed %.02f minutes.' % (training_duration))
	print('To apply the trained model, set "outputOnly" to True, and set id for "loadModelTest". E.g. "out 1 loadModelTest %d".' % test_folder_no)
	
else:
	model.load_weights( load_path )
	print("Model restored from %s." % load_path)

	batch_xs, batch_ys = tiCr.tile_inputs_all_complete, tiCr.tile_outputs_all_complete # old, inputs_test, outputs_test
	tdataSize = len(batch_xs)
	#print( format( tdataSize))
	batch_xs = np.reshape( batch_xs, [tdataSize,tileSizeLow,tileSizeLow,  n_inputChannels] )
	batch_ys = np.reshape( batch_ys, [tdataSize,tileSizeHigh,tileSizeHigh,1 ] )
	resultTiles = model.predict( batch_xs )
	#print( format( resultTiles.shape ) )

	# simply concat tiles into images...
	tileSizeHiCrop = upRes * cropTileSizeLow
	tilesPerImg = (simSizeHigh // tileSizeHiCrop) ** 2
	img_count = len(tiCr.tile_inputs_all_complete) / tilesPerImg
	tiCr.debugOutputPngsCrop(resultTiles, tileSizeHigh, simSizeHigh, test_path, \
		imageCounter=1, cut_output_to=tileSizeHiCrop, tiles_in_image=tilesPerImg)

	print('Output finished, %d pngs written to %s.' % (img_count, test_path) )

exit(1)




# ---------------------------------------------
if 0:
	x = tf.placeholder(tf.float32, shape=[None, n_input])
	y_true = tf.placeholder(tf.float32, shape=[None, n_output])
	keep_prob = tf.placeholder(tf.float32)

	xIn = tf.reshape(x, shape=[-1, tileSizeLow, tileSizeLow, n_inputChannels]) 
	cae = ConvolutionalAutoEncoder(xIn) 

	# --- main graph setup ---

	pool = 4
	# note - for simplicity, we always reduce the number of channels to 8 here 
	# this is probably suboptimal in general, but keeps the network structure similar and simple
	clFMs = int(8 / n_inputChannels)
	cae.convolutional_layer(clFMs, [3, 3], tf.nn.relu)
	cae.max_pool([pool,pool], [pool,pool])

	flat_size = cae.flatten()
	cae.fully_connected_layer(flat_size, tf.nn.relu)
	cae.unflatten()

	cae.max_depool([pool,pool], [pool,pool])
	cae.deconvolutional_layer(4, [3, 3], tf.nn.relu)

	cae.max_depool([pool,pool], [pool,pool])
	cae.deconvolutional_layer(2, [5, 5], tf.nn.relu)

	y_pred = tf.reshape( cae.y(), shape=[-1, (tileSizeHigh) *(tileSizeHigh)* 1])
	print ("DOFs: %d " % cae.getDOFs())

	costFunc = tf.nn.l2_loss(y_true - y_pred) 
	optimizer = tf.train.AdamOptimizer(learningRate).minimize(costFunc)


# create session and saver
sess = tf.InteractiveSession()
saver = tf.train.Saver()

# init vars or load model
if loadModelTest == -1:
	sess.run(tf.global_variables_initializer())
else:
	saver.restore(sess, load_path)
	print("Model restored from %s." % load_path)


# load test data
if (fileFormat == "npz"):
	tiCr.loadTestDataNpz(fromSim, toSim, emptyTileValue, cropTileSizeLow, cropOverlap, 0.95, 0.05, load_vel=useVelocities, low_res_size=simSizeLow, upres=upRes, keepAll=keepAll)
elif (fileFormat == "uni"):
	tiCr.loadTestDataUni(fromSim, toSim, emptyTileValue, cropTileSizeLow, cropOverlap, 0.95, 0.05, load_vel=useVelocities, low_res_size=simSizeLow, upres=upRes)
else:
	print("\n ERROR: Unknown file format \"" + fileFormat + "\". Use \"npz\" or \"uni\".")
	exit()


# create a summary to monitor cost tensor
lossTrain  = tf.summary.scalar("loss",     costFunc)
lossTest   = tf.summary.scalar("lossTest", costFunc)
merged_summary_op = tf.summary.merge_all() 
summary_writer    = tf.summary.FileWriter(test_path, sess.graph)

# ---------------------------------------------
# START TRAINING
training_duration = 0.0
cost = 0.0
save_no = 0

if not outputOnly:
	try:
		print('\n*****TRAINING STARTED*****\n')
		print('(stop with ctrl-c)')
		avgCost = 0
		startTime = time.time()
		epochTime = startTime
		lastSave = 1
		lastCost = 1e10
		for epoch in range(trainingEpochs):
			batch_xs, batch_ys = tiCr.selectRandomTiles(batchSize)
			_, cost, summary = sess.run([optimizer, costFunc, lossTrain], feed_dict={x: batch_xs, y_true: batch_ys, keep_prob: dropout})

			# save model
			if ((cost < lastCost) or alwaysSave) and (lastSave >= saveInterval):
				saver.save(sess, test_path + 'model_%04d.ckpt' % save_no)
				save_no += 1
				lastSave = 1
				lastCost = cost
				print('Saved Model with cost %f.' % cost)
			else:
				lastSave += 1

			# display error
			avgCost += cost
			if (epoch + 1) % testInterval == 0:
				accumulatedCost = 0.0
				for curr in range(numTests):
					batch_xs, batch_ys = tiCr.selectRandomTiles(batchSize, isTraining=False)
					cost_test, summary_test = sess.run([costFunc, lossTest], feed_dict={x: batch_xs, y_true: batch_ys, keep_prob: 1.})
					accumulatedCost += cost_test
				accumulatedCost /= numTests

				avgCost /= testInterval
				print('\nEpoch {:04d}/{:04d} - Cost= {:.9f} - Cost_test= {:.9f}'.format((epoch + 1), trainingEpochs, avgCost, accumulatedCost))
				print('%d epochs took %.02f seconds.' % (testInterval, (time.time() - epochTime)))
				#print('Estimated time: %.02f minutes.' % ((trainingEpochs - epoch) / testInterval * (time.time() - epochTime) / 60.0))
				epochTime = time.time()
				summary_writer.add_summary(summary, epoch)
				summary_writer.add_summary(summary_test, epoch)
				avgCost = 0

	except KeyboardInterrupt:
		pass

	print('\n*****TRAINING FINISHED*****')
	training_duration = (time.time() - startTime) / 60.0
	print('Training needed %.02f minutes.' % (training_duration))
	print('To apply the trained model, set "outputOnly" to True, and insert numbers for "loadModelTest", and "loadModelNo" (optional). E.g. "out 1 loadModelTest 42".')

else: 

	# ---------------------------------------------
	# outputOnly: apply to a full data set, and re-create full outputs from tiles

	batch_xs, batch_ys = tiCr.tile_inputs_all_complete, tiCr.tile_outputs_all_complete
	tileSizeHiCrop = upRes * cropTileSizeLow
	tilesPerImg = (simSizeHigh // tileSizeHiCrop) ** 2

	img_count = 0
	outrange = len(tiCr.tile_inputs_all_complete) / tilesPerImg

	# use int to avoid TypeError: 'float' object cannot be interpreted as an integer
	for currOut in range( int(outrange) ): 
		batch_xs = []
		batch_ys = []
		for curr_tile in range(tilesPerImg):
			idx = currOut * tilesPerImg + curr_tile
			batch_xs.append(tiCr.tile_inputs_all_complete[idx])
			batch_ys.append(np.zeros((tileSizeHigh * tileSizeHigh), dtype='f'))

		resultTiles = y_pred.eval(feed_dict={x: batch_xs, y_true: batch_ys, keep_prob: 1.})

		tiCr.debugOutputPngsCrop(resultTiles, tileSizeHigh, simSizeHigh, test_path, \
			imageCounter=currOut, cut_output_to=tileSizeHiCrop, tiles_in_image=tilesPerImg)
		# optionally, output references
		#tiCr.debugOutputPngsCrop(batch_ys, tileSizeHigh, simSizeHigh, test_path+"_ref", imageCounter=currOut, cut_output_to=tileSizeHiCrop, tiles_in_image=tilesPerImg)
		img_count += 1

	print('Test finished, %d pngs written to %s.' % (img_count, test_path) )

# write summary to test overview
loaded_model = ''
if not loadModelTest == -1:
	loaded_model = ', Loaded %04d, %d' % (loadModelTest , loadModelNo)
with open(basePath + 'test_overview.txt', "a") as text_file:
	text_file.write(test_path[-10:-1] + ': {:.2f} min, {} Epochs, cost {:.4f}, {}'.format(training_duration, trainingEpochs, cost, " ") + loaded_model + '\n')

