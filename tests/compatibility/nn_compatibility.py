"""Ideal words - train on compatibility judgments

Usage:
  nn_compatibility.py --lr=<n> --batch=<n> --epochs=<n> --hidden=<n> --wdecay=<n> [--ext=<file>] [--sit] [--rel] [--ppmi] [--checkpoint=<dir>]
  nn_compatibility.py (-h | --help)
  nn_compatibility.py --version

Options:
  -h --help     Show this screen.
  --version     Show version.
  --lr=<n>      Learning rate.
  --batch=<n>   Batch size.
  --hidden=<n>  Hidden layer size.
  --wdecay=<n>  Weight decay for Adam.
  --ext=<file>  File with external vectors (FastText, BERT...)
  --sit         Process situations.
  --rel         Process relations.
  --ppmi        Uses PPMI version of predicate matrix.
  --checkpoint=<dir>        Save best model.

"""

import sys
sys.path.append('../../utils/')
import itertools
from docopt import docopt
from scipy.stats import spearmanr
from utils import read_external_vectors, read_probabilistic_matrix, read_nearest_neighbours, read_cosines, read_predicate_matrix
import torch
from torch.autograd import Variable
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import torch.utils.data as td
import numpy as np
import random
import os
from math import sqrt
from sklearn.metrics import r2_score
from sklearn.model_selection import KFold
from scipy.spatial.distance import cosine
from scipy.sparse import coo_matrix

device = torch.cuda.set_device(0)
#print(device)
#random.seed(77)



class MLP(nn.Module):
    def __init__(self,d1,d2,hiddensize):
        super(MLP, self).__init__()
        self.fc11 = nn.Linear(d1,hiddensize)
        self.fc2 = nn.Linear(2*hiddensize,hiddensize)
        self.fc3 = nn.Linear(hiddensize,d2)
        #self.drop1 = nn.Dropout(p=0.5)
    def forward(self, x):
        x11 = torch.relu(self.fc11(x[0]))
        x12 = torch.relu(self.fc11(x[1]))
        x2 = torch.relu(self.fc2(torch.cat((x11,x12),2)))
        x3 = self.fc3(x2)
        return x3

def make_input(data,vocab,pm):
    cdm1 = np.zeros((len(data),pm.shape[1]))
    cdm2 = np.zeros((len(data),pm.shape[1]))
    outm = np.zeros((len(data),1))
    for i in range(len(data)):
        v1 = pm[vocab.index(data[i][0]+".n")]
        v2 = pm[vocab.index(data[i][1]+".n")]
        #v = np.concatenate([v1,v2])
        cdm1[i] = v1
        cdm2[i] = v2
        outm[i] = np.array([float(data[i][2])])
    return cdm1,cdm2,outm

def read_compatibility_data(filename):
    compatibility_data = []
    with open(filename) as f:
        lines = f.read().splitlines()
    for l in lines:
        compatibility_data.append(l.split())
    return compatibility_data

def return_stats(data_scores):
    for i in range(2,7):
        print(i-1,"<= score <",i,sum(1 for s in data_scores if s >= i-1 and s < i))

def delete_checkpoints(checkpointsdir):
    filelist = os.listdir(checkpointsdir)
    for f in filelist:
        os.remove(os.path.join(checkpointsdir, f))

def validate(net,ids_val,words1_val,words2_val,scores_val):
    #print("VALIDATION...............")
    batch_size = 1
    val_predictions = []
    val_golds = []
    val_cosines = []
    for i in range(0,len(ids_val), batch_size):
        prediction = net([Variable(torch.FloatTensor([words1_val[ids_val[i:i+batch_size]]])).cuda(), Variable(torch.FloatTensor([words2_val[ids_val[i:i+batch_size]]])).cuda()])
        #predictions.append(prediction.data.numpy()[0])
        val_predictions.append(prediction.data.cpu().numpy()[0][0])
        val_golds.append(scores_val[ids_val[i]])
        val_cosines.append(1-cosine(words1_val[ids_val[i]],words2_val[ids_val[i]]))
        #print("PRED:",ids_val[i],cd_val[ids_val[i]],prediction.data.cpu().numpy()[0][0],"COS:",val_cosines[i],"GOLD:",val_golds[i])

    val_pred_score = spearmanr(val_predictions,val_golds)[0]
    val_cos_score = spearmanr(val_cosines,val_golds)[0]

    print("VAL PRED SCORE:",val_pred_score)
    #print("VAL COS SCORE:",val_cos_score)
    return(val_pred_score,val_cos_score)

def train_model(words1_train,words2_train,scores_train,words1_val,words2_val,scores_val,ids_train,ids_val,hiddensize,lrate,wdecay,batchsize,epochs,checkpointsdir):
    '''Initialise network'''
    net = MLP(words1_train.shape[1],scores_train.shape[1],hiddensize)
    net.cuda()
    optimizer = torch.optim.Adam(net.parameters(), lr=lrate, weight_decay=wdecay)   
    criterion = nn.MSELoss()

    total_loss = 0.0
    c=0
    batch_size = batchsize
    validation_scores = []
    current_max_score = -10000

    for epoch in range(epochs):

        #print("TRAINING...............")
        #print("Epoch {}".format(epoch))
        random.shuffle(ids_train)
        #for i in ids_train:
        for i in range(0,len(ids_train), batch_size):
            #X1, X2, Y = words1[i], words2[i], scores[i]
            X1, X2, Y = words1_train[ids_train[i:i+batch_size]], words2_train[ids_train[i:i+batch_size]], scores_train[ids_train[i:i+batch_size]]
            X1, X2, Y = Variable(torch.FloatTensor([X1]), requires_grad=True).cuda(), Variable(torch.FloatTensor([X2]), requires_grad=True).cuda(), Variable(torch.FloatTensor([Y]), requires_grad=False).cuda()
            net.zero_grad()
            output = net([X1,X2])
            #loss = criterion(output, Y, torch.Tensor([1]))
            loss = criterion(output, Y)
            loss.backward()
            optimizer.step()
            total_loss+=loss.item()
            c+=1
            print(total_loss / c)

        validation_score = validate(net,ids_val,words1_val,words2_val,scores_val)[0]
        validation_scores.append(validation_score)
        if np.argmax(validation_scores) == epoch and checkpointsdir != "":
            delete_checkpoints(checkpointsdir)
            torch.save(net, checkpointsdir+"e"+str(epoch))
        #print(validation_scores)
        #print(current_max_score)
        if epoch % 100 == 0:
            if validation_scores[-1] > current_max_score:
                current_max_score = validation_scores[-1]
            else:
                print("Early stopping...")
                break

    print("MAX:", np.argmax(validation_scores), np.max(validation_scores))
    return np.max(validation_scores)

def prepare_data(external_vector_file,basedir):
    #print(external_vector_file)
    if external_vector_file != "":
        vocab, pm = read_external_vectors(external_vector_file)
        vocab = [w+".n" for w in vocab]
        #print(vocab)
    else:
        #print("Reading probabilistic matrix... Please be patient...")
        #vocab, pm = read_probabilistic_matrix(basedir)
        vocab, pm = read_predicate_matrix(basedir,ppmi=False,pca=True)

    print("Reading dataset...")
    cd_train = read_compatibility_data('data/in_vg_compatibility.train.txt')
    cd_val = read_compatibility_data('data/in_vg_compatibility.val.txt')
    cd_test = read_compatibility_data('data/in_vg_compatibility.test.txt')

    words1_train,words2_train,scores_train = make_input(cd_train,vocab,pm)
    words1_val,words2_val,scores_val = make_input(cd_val,vocab,pm)
    words1_test,words2_test,scores_test = make_input(cd_test,vocab,pm)

    print("# TRAIN STATS")
    return_stats(scores_train)
    print("# VAL STATS")
    return_stats(scores_val)
    print("# TEST STATS")
    return_stats(scores_test)

    ids_train = np.array([i for i in range(words1_train.shape[0])])
    ids_val = np.array([i for i in range(words1_val.shape[0])])
    ids_test = np.array([i for i in range(words1_test.shape[0])])

    return words1_train,words2_train,scores_train,words1_val,words2_val,scores_val,ids_train,ids_val


if __name__ == '__main__':
    basedir = "syn"
    checkpointsdir = "./checkpoints/eva/synattrel/"
    external_vector_file = ""
    args = docopt(__doc__, version='Ideal Words 0.1')
    if not args["--sit"] and args["--rel"]:
        basedir = "synrel"
    if args["--att"] and args["--rel"]:
        basedir = "synattrel"
    if args["--ext"]:
        external_vector_file = args["--ext"]
        if "fasttext" in external_vector_file:
            checkpointsdir = "./checkpoints/fasttext/final/10/"
        else:
            checkpointsdir = "./checkpoints/bert/final/10/"
    if args["--checkpoint"]:
        checkpointsdir = args["--checkpoint"]
    lrate = float(args["--lr"])
    batchsize = int(args["--batch"])
    epochs = int(args["--epochs"])
    hiddensize = int(args["--hidden"])
    wdecay = float(args["--wdecay"])

    if checkpointsdir != "":
        delete_checkpoints(checkpointsdir)
    words1_train,words2_train,scores_train,words1_val,words2_val,scores_val,ids_train,ids_val = prepare_data(external_vector_file,basedir)
    train_model(words1_train,words2_train,scores_train,words1_val,words2_val,scores_val,ids_train,ids_val,hiddensize,lrate,wdecay,batchsize,epochs,checkpointsdir)

