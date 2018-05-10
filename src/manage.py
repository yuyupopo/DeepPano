'''

python3 manage.py genData (marginType) (inputFileName)

or

python3 manage.py decideTarget (updateFileName)

'''

import sys
import os
import pandas as pd
import xml.etree.ElementTree as et
import numpy as np
import cv2
from psd_tools import PSDImage
import time
import datetime
import copy
import re


def __main__():
    
    if len(sys.argv) < 2:
        print('need to input commands\n',
                'genData (marginType) (autoSeg) (targetGen) (inputFileName), or\n',
                'decideTarget (updateFileName)')
        return
    
    command = str(sys.argv[1])
    
    if command == "genData":
        if len(sys.argv) != 6:
            # autoSeg: 0 (don't autogenerate) 1 (auto - simple) 2 (auto - complex)
            # targetGen: 0 (don't generate) 1 (auto - simple) 2 (auto - complex)
            print('need to input marginType autoSeg targetGen and inputFileName\n')
            return
        marginType = int(sys.argv[2])
        autoSeg = int(sys.argv[3])
        targetGen = int(sys.argv[4])
        inputFileName = str(sys.argv[5])
        generateDataset(marginType, autoSeg, targetGen, inputFileName)
    elif command == "decideTarget":
        if len(sys.argv) != 3:
            print('need to input updateFileName\n')
            return
        updateFileName = str(sys.argv[2])
        decideTarget(updateFileName)

    return


def decideTarget(updateFileName):

    try:
        inputDf = pd.read_csv(updateFileName)
    except IOError:
        print('cannot read input file')
        return

    rowNum, colNum = inputDf.shape
    if colNum != 16:
        print('wrong number of columns')
        return

    # TODO: columns check?

    outCols = ['Cropped.Pano.Img', 'Cropped.Box.Img', 'Cropped.Input.Img', 'Cropped.Annot.Img',
            'Left.Upmost.Coord', 'Cropped.Img.Size', 'Tooth.Num.Panoseg', 'Tooth.Num.Annot',
            'Max.IOU', '2nd.Max.IOU', 'Box.IOU', 'Margin.Type', 'Segmentable.Type', 'Target.Img',
            'Train.Val']
    rows = []

    for idx, row in inputDf.iterrows():
        rows.append(generateTargetImage(row))

    outputDf = pd.DataFrame(rows, columns=outCols)
    outputDf.to_csv(updateFileName, encoding='utf-8')

    return


def generateDataset(marginType, autoSeg, targetGen, inputFileName):
    
    try:
        inputDf = pd.read_csv(inputFileName)
    except IOError:
        print('cannot read input file')
        return

    rowNum, colNum = inputDf.shape
    
    if colNum != 5: # TODO: temporary
        print('wrong number of columns')
        return

    # TODO: columns check?

    timestamp = datetime.datetime.fromtimestamp(time.mktime(time.localtime())).strftime('%Y%m%d%H%M%S')
    # TODO: should extract inputFileName from route using regex
    outputFormat = inputFileName[17:-4] + '-' + timestamp + '-' + str(marginType)
    outCsvFileName = '../data/metadata/' + outputFormat + '.csv'
    outImgPath = '../data/metadata/' + outputFormat + '/'
    if (os.path.exists(outImgPath)):
        print('directory already exists for outImgPath' + outImgPath)
        return
    else:
        os.mkdir(outImgPath)

    print('outputRoute: {}'.format(outputFormat))

    outCols = ['Cropped.Pano.Img', 'Cropped.Box.Img', 'Cropped.Input.Img', 'Cropped.Annot.Img',
            'Left.Upmost.Coord', 'Cropped.Img.Size', 'Tooth.Num.Panoseg', 'Tooth.Num.Annot',
            'Max.IOU', '2nd.Max.IOU', 'Box.IOU', 'Margin.Type', 'Segmentable.Type', 'Target.Img',
            'Train.Val']
    rows = []

    for idx, row in inputDf.iterrows():
        rows.extend(generateDatasetForEachFile(marginType, autoSeg, targetGen, outImgPath, row))
   
    outputDf = pd.DataFrame(rows, columns=outCols)
    outputDf.to_csv(outCsvFileName, encoding='utf-8')

    return


def generateTargetImage(row):

    outRow = copy.deepcopy(row.tolist())

    cropAnnotImg = cv2.imread(row['Cropped.Annot.Img'], cv2.IMREAD_GRAYSCALE)
    targetImg = cv2.copyMakeBorder(cropAnnotImg, 0, 0, 0, 0, cv2.BORDER_REPLICATE)
    segType = row['Segmentable.Type']

    imgName = re.sub('(\S*/)*(\S+)([.]jpg)', '\\2', row['Cropped.Pano.Img'])
    if (segType < 0):
        print('{} segmentable type is error {}. skip.'.format(imgName, segType))
        trainVal = outRow[-1]
        outRow = outRow[1:-2]
        outRow.append(-1)
        outRow.append(trainVal)
        return outRow

    if (segType >= 10): # not segmentable
        targetImg = np.zeros(cropAnnotImg.shape, dtype=np.uint8)

    tiName = re.sub('cropAnnotImg', 'targetImg', row['Cropped.Annot.Img'])
    cv2.imwrite(tiName, targetImg)

    print('{} segmentable type is {}. gen target Img.'.format(imgName, segType))

    trainVal = outRow[-1]
    outRow = outRow[1:-2]
    outRow.append(tiName)
    outRow.append(trainVal)
    return outRow



def generateDatasetForEachFile(marginType, autoSeg, targetGen, outImgPath, row):

    outRows = []

    print('row: {}'.format(row))
    imageTitle = row['Image.Title']
    panoFileName = row['Pano.File']
    xmlFileName = row['Xml.File']
    annotFileName = row['Annot.File']

    panoImg = cv2.flip(cv2.imread(panoFileName, cv2.IMREAD_GRAYSCALE), 0)
    annotPsd = PSDImage.load(annotFileName)
    
    #if panoImg.shape != annotImg.shape:
    #    print('panoFile and annotFile sizes do not match')
    #    return

    imgShape = panoImg.shape
    
    
    # XML Parsing
    root = et.parse(xmlFileName).getroot()

    for tooth in root.iter('Tooth'):

        print(tooth.attrib)
        toothNum = int(tooth.attrib['Number'])
        coords = genCoordsFromTooth(tooth)
        
        cropPanoImg = cv2.copyMakeBorder(panoImg, 0, 0, 0, 0, cv2.BORDER_REPLICATE) # flipped
        leftMostCoor, cropPanoImg = cropImageWithMargin(cropPanoImg, coords, marginType, imgShape)
        cropPanoImg = cv2.flip(cropPanoImg, 0) # unflip

        print('img size: {}'.format(cropPanoImg.shape))

        boxImg = np.zeros(imgShape, dtype=np.uint8)
        boxImg = genBoxImage(boxImg, coords) # flipped
        leftMostCoor, cropBoxImg = cropImageWithMargin(boxImg, coords, marginType, imgShape)
        cropBoxImg = cv2.flip(cropBoxImg, 0) # unflip
        
        # Leave it for debugging usage
        inputImg = cv2.copyMakeBorder(cropPanoImg, 0, 0, 0, 0, cv2.BORDER_REPLICATE)
        cv2.addWeighted(cv2.add(cropPanoImg, cropBoxImg), 0.2, inputImg, 0.8, 0, inputImg)
        
        maxIOU, sndMaxIOU, boxIOU, annotToothNum, annotImg = genAnnotImage(annotPsd, boxImg, imgShape) # flipped
        leftMostCoor, cropAnnotImg = cropImageWithMargin(annotImg, coords, marginType, imgShape)
        cropAnnotImg = cv2.flip(cropAnnotImg, 0) # unflip

        segType = -1 if autoSeg == 0 else decideSegType(autoSeg, maxIOU, sndMaxIOU, boxIOU)
        targetImg = None if targetGen == 0 else genTargetImage(targetGen, segType, maxIOU, cropAnnotImg, cropBoxImg)

        # TODO: Wrong tooth number check?

        # TODO: calculate imageTitle from panoFileName and delete imageTitle column from .csv
        cpiName = outImgPath + 'cropPanoImg' + '-' + imageTitle + '-' + str(toothNum) + '.jpg'
        cbiName = outImgPath + 'cropBoxImg' + '-' + imageTitle + '-' + str(toothNum) + '.jpg'
        iiName = outImgPath + 'inputImg' + '-' + imageTitle + '-' + str(toothNum) + '.jpg'
        caiName = outImgPath + 'cropAnnotImg' + '-' + imageTitle + '-' + str(toothNum) + '.jpg'
        tiName = -1 if targetGen == 0 else re.sub('cropPanoImg', 'targetImg', cpiName)

        # export images
        cv2.imwrite(cpiName, cropPanoImg)
        cv2.imwrite(cbiName, cropBoxImg)
        cv2.imwrite(iiName, inputImg)
        cv2.imwrite(caiName, cropAnnotImg)
        if targetGen > 0:
            cv2.imwrite(tiName, targetImg)

        # for debugging purpose only
        if targetGen > 0:
            allImg = cv2.copyMakeBorder(inputImg, 0, 0, 0, 0, cv2.BORDER_REPLICATE)
            cv2.addWeighted(cv2.add(inputImg, targetImg), 0.6, allImg, 0.4, 0, allImg)
            aiName = re.sub('cropPanoImg', 'allImg', cpiName)
            cv2.imwrite(aiName, allImg)

        # write row for .csv
        newRow = [cpiName, cbiName, iiName, caiName, leftMostCoor, cropPanoImg.shape, toothNum,
                annotToothNum, maxIOU, sndMaxIOU, boxIOU, marginType, segType, tiName, row['Train.Val']]
        outRows.append(newRow)

    return outRows


def genBoxImage(img, coords):

    x1, y1, x2, y2 = 5000, 5000, 0, 0

    for i in range(4):
        cv2.line(img, coords[i], coords[(i+1)%4], 255, 1)
        x, y = coords[i]
        if x < x1:
            x1 = x
        if y < y1:
            y1 = y
        if x > x2:
            x2 = x
        if y > y2:
            y2 = y
    
    h, w = img.shape[:2]
    mask = np.zeros((h+2, w+2), dtype=np.uint8)
    print('x1: {}, y1: {}, x2: {}, y2: {}'.format(x1, y1, x2, y2))
    cv2.floodFill(img, mask, (int((x1+x2)/2), int((y1+y2)/2)), 255)
    
    return img


def genAnnotImage(annotPsd, boxImg, imgShape):

    maxIOU = 0
    sndMaxIOU = 0
    boxIOU = 0
    maxIOULayer = None
    maxIOULayerImg = np.zeros(imgShape, dtype=np.uint8)

    for layer in annotPsd.layers:
        if layer is None or layer.bbox == (0, 0, 0, 0):
            continue
        layerImg = np.array(layer.as_PIL())

        # get alpha channel from png and convert to grayscale
        if (layerImg.shape[-1] != 4):
            # Then this is background image
            continue
        r, g, b, a = cv2.split(layerImg)
        layerImg = cv2.merge([a, a, a])
        layerImg = cv2.cvtColor(layerImg, cv2.COLOR_BGR2GRAY)
        ret, layerImg = cv2.threshold(layerImg, 200, 255, cv2.THRESH_BINARY)

        annotImg = np.zeros(imgShape, dtype=np.uint8)
        b1, b2 = layer.bbox.y1, layer.bbox.y2
        b3, b4 = layer.bbox.x1, layer.bbox.x2
        annotImg[b1:b2, b3:b4] = layerImg
        annotImg = cv2.flip(annotImg, 0)

        intersectionImg = cv2.bitwise_and(annotImg, boxImg)
        intersectionArea = np.sum(intersectionImg == 255)
        teethArea = np.sum(annotImg == 255)
        boxArea = np.sum(boxImg == 255)
        thisIOU = intersectionArea / teethArea
        thisBoxIOU = intersectionArea / boxArea

        if thisIOU > 0:
            print ('layerName: {}, thisIOU: {}'.format(layer.name, thisIOU))
        if (maxIOU <  thisIOU):
            sndMaxIOU = maxIOU
            maxIOU = thisIOU
            boxIOU = thisBoxIOU
            maxIOULayer = layer
            maxIOULayerImg = annotImg
        elif (sndMaxIOU < thisIOU):
            sndMaxIOU = thisIOU

    #if maxIOU < 0.8:
    #    maxIOULayer = None
    #    maxIOULayerImg = np.zeros(imgShape, dtype=np.uint8)

    return ((maxIOU, sndMaxIOU, boxIOU, 0, maxIOULayerImg) if maxIOULayer is None
            else (maxIOU, sndMaxIOU, boxIOU, maxIOULayer.name, maxIOULayerImg))

def genTargetImage(targetGen, segType, maxIOU, cropAnnotImg, cropBoxImg):
    if targetGen == 0:
        return None
    if targetGen == 1:
        if segType < 10:
            return cv2.copyMakeBorder(cropAnnotImg, 0, 0, 0, 0, cv2.BORDER_REPLICATE)
        return np.zeros(cropAnnotImg.shape, dtype=np.uint8)
    if targetGen == 2:
        intersectionImg = cv2.bitwise_and(cropAnnotImg, cropBoxImg)
        intersectionArea = np.sum(intersectionImg == 255)
        teethArea = np.sum(cropAnnotImg == 255)
        newMaxIOU = intersectionArea / teethArea
        #if maxIOU < 0.05 or (maxIOU / newMaxIOU) < 0.67:
        if maxIOU < 0.12:
            return np.zeros(cropAnnotImg.shape, dtype=np.uint8)
        return cv2.copyMakeBorder(cropAnnotImg, 0, 0, 0, 0, cv2.BORDER_REPLICATE)
    return None

def decideSegType(autoSeg, maxIOU, sndMaxIOU, boxIOU):
    if autoSeg == 0:
        return -1
    if autoSeg == 1:
        if maxIOU < 0.3 and boxIOU < 0.3:
            return 10 # no teeth
        if maxIOU > 0.67:
            if (maxIOU * 0.67) < sndMaxIOU:
                return 12 # two teeth
            return 4 # inclusive
        if (maxIOU * 0.67) < sndMaxIOU:
            return 11 # half half
        return 5 # half inclusive
    return -3

def genCoordsFromTooth(tooth):
    return [(int(coord.attrib['X']), int(coord.attrib['Y'])) for coord in tooth]


def cropImageWithMargin(img, coords, marginType, imgShape):
    marginFuns = {1: _cropImageWithMargin1, 2: _cropImageWithMargin2, 3: _cropImageWithMargin3,
            4: _cropImageWithMargin4, 5: _cropImageWithMargin5, 6: _cropImageWithMargin6,
            7: _cropImageWithMargin7, 8: _cropImageWithMargin8, 9: _cropImageWithMargin9}
    return marginFuns[marginType](img, coords, imgShape)


def __cropImageWithSimpleMargin(img, coords, marginList, imgShape):

    x1, x2, y1, y2 = 5000, 0, 5000, 0

    for coord in coords:
        x = coord[0]
        y = coord[1]

        if x < x1:
            x1 = x
        if y < y1:
            y1 = y
        if x > x2:
            x2 = x
        if y > y2:
            y2 = y

    x1 = (x1 - marginList[0]) if ((x1 - marginList[0]) > 0) else 0
    x2 = (x2 + marginList[1]) if ((x2 + marginList[0]) < imgShape[1]) else imgShape[1]
    y1 = (y1 - marginList[2]) if ((y1 - marginList[2]) > 0) else 0
    y2 = (y2 + marginList[3]) if ((y2 + marginList[3]) < imgShape[0]) else imgShape[0]

    return ((x1, y1), img[y1:y2, x1:x2])


def _cropImageWithMargin1(img, coords, imgShape):
    return __cropImageWithSimpleMargin(img, coords, [40, 40, 40, 40], imgShape)

def _cropImageWithMargin2(img, coords, imgShape):
    return __cropImageWithSimpleMargin(img, coords, [50, 50, 80, 80], imgShape)

def _cropImageWithMargin3(img, coords, imgShape):
    return __cropImageWithSimpleMargin(img, coords, [80, 80, 80, 80], imgShape)

def _cropImageWithMargin4(img, coords, imgShape):
    return __cropImageWithSimpleMargin(img, coords, [60, 60, 100, 100], imgShape)

def _cropImageWithMargin5(img, coords, imgShape):
    return __cropImageWithSimpleMargin(img, coords, [100, 100, 100, 100], imgShape)

def _cropImageWithMargin6(img, coords, imgShape):
    return __cropImageWithSimpleMargin(img, coords, [200, 200, 200, 200], imgShape)

def _cropImageWithMargin7(img, coords, imgShape):
    return __cropImageWithSimpleMargin(img, coords, [400, 400, 400, 400], imgShape)

def _cropImageWithMargin8(img, coords, imgShape):
    return __cropImageWithSimpleMargin(img, coords, [60, 60, 120, 120], imgShape)

def _cropImageWithMargin9(img, coords, imgShape):
    return __cropImageWithSimpleMargin(img, coords, [70, 70, 150, 150], imgShape)

if __name__ == '__main__':
    __main__()
