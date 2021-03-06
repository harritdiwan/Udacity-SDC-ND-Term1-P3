import numpy as np
import tensorflow as tf
import csv
import matplotlib.pyplot as plt
import os, sys
import cv2
from sklearn.model_selection import train_test_split
from keras.models import Sequential, Model
from keras.layers.core import Dense, Dropout, Activation,Lambda
from keras.optimizers import Adam
from keras.utils import np_utils
from keras.layers import Convolution2D, MaxPooling2D, Flatten, Input, ELU
from keras import initializations
from keras.models import load_model, model_from_json
from keras.layers.normalization import BatchNormalization
from sklearn.utils import shuffle
from keras import backend as K
import json
import gc

# udacity data
csv_path1 = 'driving_log.csv'   

center_db, left_db, right_db, steer_db = [], [], [], []
Rows, Cols = 100, 100
offset = 0.22

# read csv file
with open(csv_path1) as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        if float(row['steering']) != 0.0:
            center_db.append(row['center'])
            left_db.append(row['left'].strip())
            right_db.append(row['right'].strip())
            steer_db.append(float(row['steering']))
        else:
            prob = np.random.uniform()
            if prob <= 0.15:
                center_db.append(row['center'])
                left_db.append(row['left'].strip())
                right_db.append(row['right'].strip())
                steer_db.append(float(row['steering']))

                
# shuffle a dataset
center_db, left_db, right_db, steer_db = shuffle(center_db, left_db, right_db, steer_db)


# split train & valid data
img_train, img_valid, steer_train, steer_valid = train_test_split(center_db, steer_db, test_size=0.1, random_state=42)


def select_img(center, left, right, steer, num, offsets=0.22):
    """
    randomly select among center, left, right images
    add ±0.22 to left, right steering angle.
    """
    rand = np.random.randint(3)
    if rand == 0:
        image, steering = cv2.imread(center[num]), steer[num]
    elif rand == 1:
        image, steering = cv2.imread(left[num]), steer[num] + offsets
    elif rand == 2:
        image, steering = cv2.imread(right[num]), steer[num] - offsets
    if abs(steering) > 1:
        steering = -1 if (steering < 0) else 1

    return image, steering



def valid_img(valid_image, valid_steer, num):
    """ using only center image for validation """
    steering = valid_steer[num]
    image = cv2.imread(valid_image[num])
    return image, steering



def resize_img(image):
    """ crop unnecessary parts """
    image = image[55:159, 0:319]
    resized_img = cv2.resize(image, (Cols, Rows), cv2.INTER_AREA)
    img = cv2.cvtColor(resized_img, cv2.COLOR_BGR2RGB)
    return resized_img



def shift_img(image, steer):
    """
    randomly shift image horizontally to simulate scenes in which car goes to the edge of the road and has to steer back to the center
    add proper steering angle to each image
    """
    max_shift = 55
    max_ang = 0.14
    rows, cols, _ = image.shape
    random_x = np.random.randint(-max_shift, max_shift + 1)
    dst_steer = steer + (random_x / max_shift) * max_ang
    if abs(dst_steer) > 1:
        dst_steer = -1 if (dst_steer < 0) else 1

    mat = np.float32([[1, 0, random_x], [0, 1, 0]])
    dst_img = cv2.warpAffine(image, mat, (cols, rows))
    return dst_img, dst_steer



def flip_img(image, steering):
    """ randomly flip image to gain right turn data (track1 is biased in left turn) """
    flip_image = image.copy()
    flip_steering = steering
    num = np.random.randint(2)
    if num == 0:
        flip_image, flip_steering = cv2.flip(image, 1), -steering
    return flip_image, flip_steering



def network_model():
    """
    designed with 5 convolutional layer & 4 fully connected layer
    activation func : relu
    pooling : maxpooling
    used dropout
    """
    model = Sequential()
    model.add(Lambda(lambda x: x / 127.5 - 1.0, input_shape=(100, 100, 3)))
    model.add(Convolution2D(32, 3, 3, border_mode='same', subsample=(2, 2), activation='relu', name='Conv1'))
    model.add(MaxPooling2D(pool_size=(2, 2), strides=None, border_mode='same'))
    model.add(Convolution2D(64, 3, 3, border_mode='same', subsample=(2, 2), activation='relu', name='Conv2'))
    model.add(MaxPooling2D(pool_size=(2, 2), strides=None, border_mode='same'))
    model.add(Convolution2D(128, 3, 3, border_mode='same', subsample=(1, 1), activation='relu', name='Conv3'))
    model.add(MaxPooling2D(pool_size=(2, 2), strides=None, border_mode='same'))
    model.add(Convolution2D(128, 2, 2, border_mode='same', subsample=(1, 1), activation='relu', name='Conv4'))
    model.add(MaxPooling2D(pool_size=(2, 2), strides=None, border_mode='same'))
    model.add(Convolution2D(256, 2, 2, border_mode='same', subsample=(1, 1), activation='relu', name='Conv5'))
    model.add(Flatten())
    model.add(Dropout(0.2))
    model.add(Dense(256, activation='relu', name='FC1'))
    model.add(Dropout(0.5))
    model.add(Dense(128, activation='relu', name='FC2'))
    model.add(Dropout(0.5))
    model.add(Dense(64, activation='relu', name='FC3'))
    model.add(Dense(1))
    return model



def generate_train(center, left, right, steer):
    """
    data augmentation
    transformed image & resized them
    """
    num = np.random.randint(0, len(steer))
    image, steering = select_img(center, left, right, steer, num, offset)
    image, steering = shift_img(image, steering)
    image, steering = flip_img(image, steering)
    image = resize_img(image)
    return image, steering



def generate_valid(img_valid, steer_valid):
    """ generate validation set """
    img_set = np.zeros((len(img_valid), Rows, Cols, 3))
    steer_set = np.zeros(len(steer_valid))
    for i in range(len(img_valid)):
        img, steer = valid_img(img_valid, steer_valid, i)
        img_set[i] = resize_img(img)

        steer_set[i] = steer
    return img_set, steer_set



def generate_train_batch(center, left, right, steering, batch_size):
    """ compose training batch set """
    image_set = np.zeros((batch_size, Rows, Cols, 3))
    steering_set = np.zeros(batch_size)

    while 1:
        for i in range(batch_size):
            img, steer = generate_train(center, left, right, steering)
            image_set[i] = img
            steering_set[i] = steer
        yield image_set, steering_set

        
batch_size = 200
epoch = 9


train_generator = generate_train_batch(center_db, left_db, right_db, steer_db, batch_size)
image_val, steer_val = generate_valid(img_valid, steer_valid)

model = network_model()

adam = Adam(lr=1e-4, beta_1=0.9, beta_2=0.999, epsilon=1e-08, decay=0.0)
model.compile(optimizer=adam, loss='mse')

model_json = 'model.json'
model_weights = 'model.h5'

history = model.fit_generator(train_generator, samples_per_epoch=20480, nb_epoch=epoch,
                              validation_data=(image_val, steer_val), verbose=1)

json_string = model.to_json()

try:
    os.remove(model_json)
    os.remove(model_weights)
except OSError:
    pass

with open(model_json, 'w') as jfile:
    json.dump(json_string, jfile)
model.save_weights(model_weights)

# to avoid " 'NoneType' object has no attribute 'TF_DeleteStatus' " error
gc.collect()
K.clear_session()
