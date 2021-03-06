import numpy as np
from sklearn.model_selection import train_test_split
# from keras.callbacks import ModelCheckpoint
import numpy as np
import pickle
import sys
from collections import defaultdict
import shap
from torchvision import transforms, datasets
import torchvision
from sklearn.metrics import roc_curve, auc, roc_auc_score
from keras.models import load_model
import tensorflow as tf
from keras import backend as K
import matplotlib.pyplot as plt
from tqdm import     tqdm
from models import mahalanobis_resnet as mres
import time
import torch
import matplotlib.pyplot as plt


def get_loaders(dataset):
    if dataset == 'MNIST':
        pass

    if dataset == 'CIFAR10':
        transform = transforms.Compose([transforms.ToTensor()])
        trainset = torchvision.datasets.CIFAR10(root='./data', train=True, download=True, transform=transform)
        trainloader = torch.utils.data.DataLoader(trainset, batch_size=256, shuffle=True, num_workers=20)
        testset = torchvision.datasets.CIFAR10(root='./data', train=False, download=True, transform=transform)
        testloader = torch.utils.data.DataLoader(testset, batch_size=32, shuffle=False, num_workers=20)
        # classes = ('plane', 'car', 'bird', 'cat', 'deer', 'dog', 'frog', 'horse', 'ship', 'truck')
        return trainloader, testloader

    if dataset == 'SVHN':
        transform = transforms.Compose([transforms.ToTensor()])
        trainset = torchvision.datasets.SVHN(root='./data', split='train', download=True, transform=transform)
        trainloader = torch.utils.data.DataLoader(trainset, batch_size=100, shuffle=False, num_workers=20)
        testset = torchvision.datasets.SVHN(root='./data', split='test', download=True, transform=transform)
        testloader = torch.utils.data.DataLoader(testset, batch_size=100, shuffle=False, num_workers=20)
        return trainloader, testloader
    print('loaders error!')


def get_deep_explainer(trainloader, net):
    batch = next(iter(trainloader))
    images, labels = batch
    background = images[:100]
    e = shap.DeepExplainer(net, background.to('cuda'))
    return e


def get_xai_channels(X, e):
    if type(X).__module__ == np.__name__:
        data = (torch.from_numpy(X)).to('cuda')
    else:
        data = X
    shap_values = e.shap_values(data.float())
    return np.transpose(np.array(shap_values), (1, 0, 2, 3, 4))


def plot_roc_multi(y_test, preds=[], classes=[], filename='tmp'):
    # plt.figure(figsize=(15, 10))
    plt.rcParams.update({'font.size': 20})
    plt.rc('axes', titlesize=20)
    plt.rc('axes', labelsize=20)
    plt.rc('xtick', labelsize=20)
    plt.rc('ytick', labelsize=20)


    fpr, tpr, roc_auc = dict(), dict(), dict()
    for i in range(len(preds)):
        fpr[i], tpr[i], _ = roc_curve(y_test, preds[i])
        roc_auc[i] = auc(fpr[i], tpr[i])

    # plt.figure()
    lw = 2
    for i in range(len(preds)):
        plt.plot(fpr[i], tpr[i], lw=lw, label='%s (area = {%0.2f})' % (classes[i], roc_auc[i]))

    #     plt.plot(fpr, tpr, color='darkorange', lw=lw, label='ROC curve (area = %0.2f)' % roc_auc)
    plt.plot([0, 1], [0, 1], color='navy', lw=lw, linestyle='--')
    plt.xlim([0.0, 1.0])
    plt.ylim([0.0, 1.05])
    plt.xlabel('False Positive Rate')
    plt.ylabel('True Positive Rate')
    # plt.title(filename.split('/')[-1])
    plt.legend(loc="lower right")
    plt.savefig(filename + '.png')
    return roc_auc

def kauc(y_true, y_pred):
    kauc = tf.metrics.auc(y_true, y_pred)[1]
    K.get_session().run(tf.local_variables_initializer())
    return kauc

with open('../explanations/CIFAR10/resnet/natural.pkl', 'rb') as f:
    cifar = pickle.load(f)


with open('../explanations/SVHN/resnet/natural.pkl', 'rb') as f:
    svhn = pickle.load(f)

svhn_resnet = mres.ResNet34(num_c=10)
svhn_resnet.load_state_dict(torch.load('../models/resnet_svhn.pth'))
svhn_resnet = svhn_resnet.to('cuda')

with open('../models/resnetxt_acc_87.pkl', 'rb') as f:
    cifar_resnet = pickle.load(f)
cifar_resnet = cifar_resnet.module

cifar_sup, cifar_unsup, svhn_sup, svhn_unsup = dict(), dict(), dict(), dict()
for n in tqdm(range(10)):
    cifar_sup[n] = load_model('../xai_models/CIFAR10/resnet/FGSM_0.1_%s.h5'%n,custom_objects={'kauc':kauc})
    cifar_unsup[n] = load_model('../xai_models/CIFAR10/resnet/None_%s.h5'%n,custom_objects={'kauc':kauc})
    svhn_sup[n] = load_model('../xai_models/SVHN/resnet/FGSM_0.1_%s.h5'%n,custom_objects={'kauc':kauc})
    svhn_unsup[n] = load_model('../xai_models/SVHN/resnet/None_%s.h5'%n,custom_objects={'kauc':kauc})



trainloader, _ = get_loaders('CIFAR10')
e_cifar = get_deep_explainer(trainloader, cifar_resnet)

trainloader, _ = get_loaders('SVHN')
e_svhn = get_deep_explainer(trainloader, svhn_resnet)

minutes_to_run = int(sys.argv[1])

t0=time.time()
in_dist_preds_sup, in_dist_preds_unsup = [], []
for batch_ind in np.array_split(range(cifar['X'].shape[0]),1000):
    data = cifar['X'][batch_ind]
    x = torch.tensor(data)
    shap_vals = get_xai_channels(data,e_cifar)

    softmax_layer = cifar_resnet(x.to('cuda').float())
    estimate_prob, estimate_class = torch.max(softmax_layer.data, 1)
    for i,c in enumerate(estimate_class):
        sample = np.concatenate((data[[i]], shap_vals[[i]][:, c.item(), :, :, :]), axis=1)
        sample = np.transpose(sample,(0,2,3,1))
        in_dist_preds_sup.append(cifar_sup[c.item()].predict(sample).item())
        in_dist_preds_unsup.append(cifar_unsup[c.item()].predict(sample).item())

    if (time.time()-t0)>(60*minutes_to_run):
        break

t0=time.time()
out_dist_preds_sup, out_dist_preds_unsup = [], []
for batch_ind in np.array_split(range(svhn['X'].shape[0]),1000):
    data = svhn['X'][batch_ind]
    x = torch.tensor(data)
    shap_vals = get_xai_channels(data,e_cifar)

    softmax_layer = cifar_resnet(x.to('cuda').float())
    estimate_prob, estimate_class = torch.max(softmax_layer.data, 1)
    for i,c in enumerate(estimate_class):
        sample = np.concatenate((data[[i]], shap_vals[[i]][:, c.item(), :, :, :]), axis=1)
        sample = np.transpose(sample,(0,2,3,1))
        out_dist_preds_sup.append(cifar_sup[c.item()].predict(sample).item())
        out_dist_preds_unsup.append(cifar_unsup[c.item()].predict(sample).item())

    if (time.time()-t0)>(60*minutes_to_run):
        break


y = [0]*len(in_dist_preds_sup) + [1]*len(out_dist_preds_sup)
y_sup_pred = in_dist_preds_sup + out_dist_preds_sup
y_unsup_pred = in_dist_preds_unsup + out_dist_preds_unsup

with open('../code/logs/OOD/y_OOD_for_cifar_%s_minutes'%minutes_to_run, 'wb') as f:
    pickle.dump(y,f)
with open('../code/logs/OOD/y_sup_pred_OOD_for_cifar_%s_minutes'%minutes_to_run, 'wb') as f:
    pickle.dump(y_sup_pred,f)
with open('../code/logs/OOD/y_unsup_pred_OOD_for_cifar_%s_minutes'%minutes_to_run, 'wb') as f:
    pickle.dump(y_unsup_pred,f)

plot_roc_multi(y, preds=[y_unsup_pred,y_sup_pred], classes=['Non_adv_detector','Adv_detector'],
               filename='../code/logs/figures/OOD_for_cifar_%s_minutes'%minutes_to_run)


t0=time.time()
in_dist_preds_sup, in_dist_preds_unsup = [], []
for batch_ind in np.array_split(range(svhn['X'].shape[0]),1000):
    data = svhn['X'][batch_ind]
    x = torch.tensor(data)
    shap_vals = get_xai_channels(data,e_svhn)

    softmax_layer = svhn_resnet(x.to('cuda').float())
    estimate_prob, estimate_class = torch.max(softmax_layer.data, 1)
    for i,c in enumerate(estimate_class):
        sample = np.concatenate((data[[i]], shap_vals[[i]][:, c.item(), :, :, :]), axis=1)
        sample = np.transpose(sample,(0,2,3,1))
        in_dist_preds_sup.append(svhn_sup[c.item()].predict(sample).item())
        in_dist_preds_unsup.append(svhn_unsup[c.item()].predict(sample).item())

    if (time.time()-t0)>(60*minutes_to_run):
        break

t0=time.time()
out_dist_preds_sup, out_dist_preds_unsup = [], []
for batch_ind in np.array_split(range(cifar['X'].shape[0]),1000):
    data = cifar['X'][batch_ind]
    x = torch.tensor(data)
    shap_vals = get_xai_channels(data,e_svhn)

    softmax_layer = svhn_resnet(x.to('cuda').float())
    estimate_prob, estimate_class = torch.max(softmax_layer.data, 1)
    for i,c in enumerate(estimate_class):
        sample = np.concatenate((data[[i]], shap_vals[[i]][:, c.item(), :, :, :]), axis=1)
        sample = np.transpose(sample,(0,2,3,1))
        out_dist_preds_sup.append(svhn_sup[c.item()].predict(sample).item())
        out_dist_preds_unsup.append(svhn_unsup[c.item()].predict(sample).item())

    if (time.time()-t0)>(60*minutes_to_run):
        break


y = [0]*len(in_dist_preds_sup) + [1]*len(out_dist_preds_sup)
y_sup_pred = in_dist_preds_sup + out_dist_preds_sup
y_unsup_pred = in_dist_preds_unsup + out_dist_preds_unsup

with open('../code/logs/OOD/y_OOD_for_svhn_%s_minutes'%minutes_to_run, 'wb') as f:
    pickle.dump(y,f)
with open('../code/logs/OOD/y_sup_pred_OOD_for_svhn_%s_minutes'%minutes_to_run, 'wb') as f:
    pickle.dump(y_sup_pred,f)
with open('../code/logs/OOD/y_unsup_pred_OOD_for_svhn_%s_minutes'%minutes_to_run, 'wb') as f:
    pickle.dump(y_unsup_pred,f)

plot_roc_multi(y, preds=[y_unsup_pred,y_sup_pred], classes=['Non_adv_detector','Adv_detector'],
               filename='../code/logs/figures/OOD_for_svhn_%s_minutes'%minutes_to_run)