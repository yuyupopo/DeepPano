
import os
import torch
import matplotlib
from torch.utils.data import DataLoader
import datetime
import time
import numpy as np
from utils import AverageMeter, GeometricMeter, ImageMeter, ClassMeter

import seaborn as sns
import itertools
import torch.nn.functional as F

import matplotlib.pyplot as plt
plt.switch_backend('agg')
import pandas as pd

def plot_confusion_matrix(output, target, threshold, title, path):
    """
    changed from stackoverflow.com/questions/5821125/how-to-plot-confusion-matrix-with-string-axis-rather-than-integer-in-python
    """

    batch_size = output.size(0)
    channel = output.size(1)

    output = output.view(batch_size, channel, -1)
    target = target.view(batch_size, channel, -1)

    output = (output > threshold).byte()
    # (batch_size, channel, ?) of 0, 1
    output = output.numpy().any(axis=2)
    target = target.numpy().any(axis=2)
    # (batch_size, channel)
    output = output.sum(axis=1)
    target = target.sum(axis=1)

    assert (output.shape == target.shape)
    # (batch_size) of 0, 1, 2

    classes = set(np.unique(target))
    classes_len = 3
    matrix = np.zeros((classes_len, classes_len))

    output = list(output)
    target = list(target)

    for o, t in zip(output, target):
        matrix[t][o] += 1

    norm_conf = matrix / matrix.sum(axis=1, keepdims=True)

    fig = plt.figure()
    plt.clf()
    ax = fig.add_subplot(111)
    ax.set_aspect(1)
    res = ax.imshow(np.array(norm_conf), cmap=plt.cm.jet, 
                    interpolation='nearest')

    width, height = 3, 3

    for x in range(width):
        for y in range(height):
            ax.annotate(str(matrix[x][y]), xy=(y, x), 
                        horizontalalignment='center',
                        verticalalignment='center')

    cb = fig.colorbar(res)
    # ax.xaxis.set_label_position('top') 
    # ax.xaxis.tick_top()
    plt.xticks(range(width), ['none', 'single', 'double'])
    plt.yticks(range(height), ['none', 'single', 'double'])
    plt.xlabel('target')
    plt.ylabel('output')
    plt.title(title)
    plt.savefig(path, format='png')
    plt.clf()

def plot_histogram(values, title, path):

    # the histogram of the data
    fig = plt.figure()
    values = [x for x in values if str(x) != 'nan']
    plt.hist(values, 50, facecolor='green', alpha=0.75)

    plt.ylabel('Samples')
    plt.title(title)
    plt.grid(True)

    plt.savefig(path)
    plt.clf()


class Inference():
    
    def __init__(self, model, datasets, metrics, visualizations, LOG):
        self.model = model
        self.datasets = datasets
        self.LOG = LOG
        self.path = LOG.log_dir_base
        self.metrics = metrics
        self.visualizations = visualizations

    def __call__(self, batch_size=30):
        dataloaders = { x: DataLoader(dataset=self.datasets[x], batch_size=batch_size) 
                for x in ['train', 'val']}

        for turn in ['train', 'val']:
            self.evaluate(turn, dataloaders)

    def evaluate(self, turn, dataloaders):
        losses = {}
        metric_results = [{} for m in self.metrics]
        output_image = ImageMeter()
        target_image = ImageMeter()

        samples = []

        # forward    
        with torch.no_grad():
            for batch_idx, (input, target, index) in enumerate(dataloaders[turn]):
                print('inference: {}th'.format(batch_idx))
                start =  time.time()
                loss, output = self.model(input, target, 'val', reduce=False)
                inferenceTime = time.time() - start
                
                output_image.update(output)
                target_image.update(target)
                
                index = list(index.numpy())
                for i, idx in enumerate(index):

                    data = {}
                    o = output[i:i+1]
                    t = target[i:i+1]
                    l = loss[i:i+1]
                    losses[idx] = l.item()
                    data['all_img_path'] = self.datasets[turn].getAllImgPath(idx)
                    data['loss'] = l.item()
                    for metric, result in zip(self.metrics, metric_results):
                        name = repr(metric).replace('/', '_')
                        m = metric(o, t)
                        result[idx] = m
                        data[name] = m

                    data['inferenceTime'] = inferenceTime

                    self.save_sample(data, o, t, 0.8)
                    self.save_sample(data, o, t, 0.5)
                    self.save_sample(data, o, t, 0.3)
                    self.save_sample(data, o, t, 0.1)
                    self.save_sample(data, o, t, 0.02)
                    self.save_sample(data, o, t, 0.01)

                    samples.append(data)

        # histogram of losses
        plot_histogram(list(losses.values()), 'loss', '{}{}/loss.png'.format(self.path, turn))
        plt.close()
        # histogram of each metrics
        for metric, result in zip(self.metrics, metric_results):
            name = repr(metric).replace('/', '_')
            plot_histogram(list(result.values()), name, '{}{}/{}.png'.format(self.path, turn, name))

        plt.close()
        plot_confusion_matrix(output_image.images, target_image.images, 0.5, 'confusion_0.5', '{}/{}/{}.png'.format(self.path, turn, 'confusion_0.5'))
        plt.close()
        df = pd.DataFrame(samples)
        df.to_csv('{}{}/result.csv'.format(self.path, turn))

        COLUMNS = [repr(m).replace('/', '_') for m in self.metrics] + ['loss']
        fig = plt.figure()
        plt.clf()
        g = sns.pairplot(df, size=3, vars=COLUMNS)
        g.savefig('{}{}/metrc.png'.format(self.path, turn))
        plt.clf()

    def save_sample(self, data, output, target, threshold):
        
        assert output.size(0) == 1
        channel = output.size(1)
        data['output_{}'.format(threshold)] = (output.view(channel, -1) > threshold).byte().numpy().any(axis=1).sum(axis=0)
        data['target_{}'.format(threshold)] = (target.view(channel, -1) > threshold).byte().numpy().any(axis=1).sum(axis=0)