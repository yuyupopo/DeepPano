"""

open, load, augment dataset

do multiprocessing
bottleneck이 되지 않도록 시간 재기
GPU utilization
"""

import os
import pickle
import torch
import numpy as np
from PIL import Image
from typing import NamedTuple
from torch.utils.data import Dataset
import pandas as pd
from augmentation import getAugmentation

IMG_EXTENSIONS = ('.png', '.jpg', '.jpeg')


def isImageFile(filename):
    """Check if a file is an slide
    
    Arguments:
        filename {string} -- path or file name 
    """
    return filename.lower().endswith(IMG_EXTENSIONS)


def getAbsoluteAddress(filedir):
    if filedir == '0':
        return None
    return os.path.join(os.path.dirname(__file__), filedir)
    

def createImage(size, blank=True):
    """create blank PIL image of size
    
    Arguments:
        size {tuple} -- size of image
    """
    if blank:
        img = np.zeros(size)
    else:
        img = np.ones(size) * 255
    img = Image.fromarray(img, mode='L')
    return img


FRONT = (11, 12, 13, 21, 22, 23, 31, 32, 33, 41, 42, 43)

class Filter():
    
    def __init__(self, filters):
        lookup = {
            "train" : lambda row: row['Train.Val'] == 'train' and int(row['Segmentable.Type']) > 0,
            "val" : lambda row: row['Train.Val'] == 'val' and int(row['Segmentable.Type']) > 0,
            "easy": lambda row: int(row['Segmentable.Type']) <= 10,
            "segmentable": lambda row: int(row['Segmentable.Type']) < 10,
            "unsegmentable": lambda row: int(row['Segmentable.Type']) >= 10,
            "front-teeth": lambda row: int(row['Tooth.Num.Annot']) in FRONT,
        }
        self.func = []
        self.func += [lookup[f] for f in filters]

    def __call__(self, row):
        for f in self.func:
            if not f(row):
                return False
        return True

class Data(NamedTuple):
    metadata_path: str
    pano_mean: float
    pano_std: float
    box_mean: float
    box_std : float

class Patch(NamedTuple):
    pano_path: str
    box_path: str
    major_input_path: str
    minor_input_path: str
    major_target_path: str
    minor_target_path: str
    all_image_path: str
    size: tuple


def getDataset(datadir, name, filter, pretrain, channel, size, train, val):
    df = pd.read_csv(datadir)
    data = df.loc[df['DataSet.Title'] == name].iloc[0]
    data = Data(data['Csv.File'], data['Pano.Mean'], data['Pano.Stdev'], data['Box.Mean'], data['Box.Stdev'])    

    data_filter = { x : Filter(filter[x]) for x in ('train', 'val')}

    augmentation_param = {
        'size': size,
        'box_mean': float(data.box_mean), 'pano_mean': float(data.pano_mean),
        'box_std': float(data.box_std), 'pano_std': float(data.pano_std),
    }

    print(augmentation_param)
    
    D = PretrainPanoSet if pretrain else PanoSet

    augmentations = {'train' : getAugmentation(train, augmentation_param),
                     'val'   : getAugmentation(val, augmentation_param)}    

    return { x: D(data.metadata_path, data_filter[x], transform=augmentations[x])
                    for x in ('train', 'val')}

class PanoSet(Dataset):
    """
    extended Dataset class for pytorch
    
    """

    def __init__(self, meta_data_path, filter_func, transform = None):
        
        self.path = meta_data_path
        df = pd.read_csv(self.path)
        data = []

        for idx, row in df.iterrows():
            if filter_func(row):
                pano_path = getAbsoluteAddress(row['Cropped.Pano.Img'])
                box_path = getAbsoluteAddress(row['Cropped.Box.Img'])
                major_input_path = getAbsoluteAddress(row['Cropped.Major.Annot.Img'])
                minor_input_path = getAbsoluteAddress(row['Cropped.Minor.Annot.Img'])
                major_target_path = getAbsoluteAddress(row['Major.Target.Img'])
                minor_target_path = getAbsoluteAddress(row['Minor.Target.Img'])
                all_image_path = getAbsoluteAddress(row['All.Img'])
                size = eval(row['Cropped.Img.Size'])

                data.append(Patch(
                    pano_path, box_path,  
                    major_input_path,  minor_input_path,
                    major_target_path, minor_target_path,
                    all_image_path,
                    size))
        
        self.data = data
        self.meta_data = df
        self.transform = transform

    def __getitem__(self, index, doTransform=True):
        """
        
        Arguments:
            index {int} -- index of slide
        Returns:
            tuple: (image, target, path, index)
                target is class_index
        """
        patch = self.data[index]

        input_pano = Image.open(patch.pano_path)
        input_box = Image.open(patch.box_path)

        if patch.major_target_path is None:
            target_major = createImage(patch.size)
        else:
            target_major = Image.open(patch.major_target_path)

        if patch.minor_target_path is None:
            target_minor = createImage(patch.size)
        else:
            target_minor = Image.open(patch.minor_target_path)

        target_major = target_major.point(lambda p: 255 if p > 50 else 0)
        target_minor = target_minor.point(lambda p: 255 if p > 50 else 0)

        if self.transform is not None and doTransform:
            input_pano, input_box, target_major, target_minor = self.transform(input_pano, input_box, target_major, target_minor)
            
        input = torch.cat([input_box, input_pano], dim=0)
        target = torch.cat([target_major, target_minor], dim=0)

        assert set(np.unique(target)).issubset({0,1})
      
        return (input, target, index)

    def getAllImgPath(self, index):
        patch = self.data[index]
        return patch.all_image_path

    def step(self):
        pass

    def __len__(self):
        return len(self.data)

    def __str__(self):
        return 'Dataset: {} [size: {}]'.format(self.__class__.__name__, len(self.data))

if __name__ == '__main__':
    print(__doc__)

class Panorama(NamedTuple):
    pano_path: str
    target_path: str
    all_path: str

class PretrainPanoSet(Dataset):
    """
    extended Dataset class for pytorch fore pretrain
    
    """

    def __init__(self, meta_data_path, filter_func, transform = None):
        
        self.path = meta_data_path
        df = pd.read_csv(self.path)
        data = []

        for idx, row in df.iterrows():
            if filter_func(row):
                pano_path = getAbsoluteAddress(row['Pano.Img'])
                target_path = getAbsoluteAddress(row['Target.Img'])
                all_path = getAbsoluteAddress(row['All.Img'])

                data.append(Panorama(pano_path, target_path, all_path))
        
        self.data = data
        self.meta_data = df
        self.transform = transform

    def __getitem__(self, index, doTransform=True):
        """
        
        Arguments:
            index {int} -- index of slide
        Returns:
            tuple: (image, target, path, index)
                target is class_index
        """
        patch = self.data[index]

        input_pano = Image.open(patch.pano_path)
        input_box = createImage(input_pano.size)
        target_major = Image.open(patch.target_path)
        target_minor = Image.open(patch.target_path) # use copy?

        target_major = target_major.point(lambda p: 255 if p > 50 else 0)
        target_minor = target_minor.point(lambda p: 255 if p > 50 else 0)

        if self.transform is not None and doTransform:
            input_pano, input_box, target_major, target_minor = self.transform(input_pano, input_box, target_major, target_minor)
            
        input = torch.cat([input_box, input_pano], dim=0)
        target = torch.cat([target_major, target_minor], dim=0)

        assert set(np.unique(target)).issubset({0,1})
      
        return (input, target, index)

    def __len__(self):
        return len(self.data)

    def __str__(self):
        return 'Dataset: {} [size: {}]'.format(self.__class__.__name__, len(self.data))

if __name__ == '__main__':
    print(__doc__)