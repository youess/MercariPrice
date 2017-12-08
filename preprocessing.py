# -*- coding: utf-8 -*-

import os
import time
import numpy as np
import pandas as pd
import scipy
import gc
import spacy
import string
from pathlib import Path
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
from scipy.sparse import csr_matrix, hstack

base_dir = Path(os.path.dirname(__file__))
train_file = base_dir / 'data/train.tsv'
test_file = base_dir / 'data/test.tsv'

print('Loading the dataset...')
tic = time.time()
train = pd.read_table(train_file)
test = pd.read_table(test_file)
toc = time.time()
_cost = (toc - tic) / 60
print('Dataset had been loaded! cost: {:.2f} min'.format(_cost))

y = train['price']
test_id = test['test_id']

train = train.drop('price', axis=1)
ntrain = train.shape[0]
data: pd.DataFrame = pd.concat([train.iloc[:, 1:], test.iloc[:, 1:]])

del train, test
gc.collect()

print(data.describe())
print(data.isnull().sum())

print('Begin to pre-processing the feature columns...')
# fill na
data['category_name'].fillna('NoCate/NoCate/NoCate', inplace=True)
data['brand_name'].fillna('NoBrand', inplace=True)
ind = data['item_description'] == 'No description yet'
data.loc[ind, 'item_description'] = np.nan
data['item_description'].fillna('', inplace=True)

# split category
data['cat1'], data['cat2'], data['cat3'] = zip(*data['category_name'].apply(lambda x: x.split('/')))
data.drop('category_name', axis=1, inplace=True)

# has brand
data['has_brand'] = (data['brand_name'] != 'NoBrand').astype(int)

# description contain remove price number
data['desc_has_price'] = data['item_description'].apply(lambda x: '[rm]' in x).astype(int)

print('Basic feature variable had been done...')

print('Begin to train word vector...')
# text mining variable
data['text'] = data['name'] + '/' + data['brand_name'] + '/' + data['item_description']

data.drop(['name', 'brand_name', 'item_description'], axis=1, inplace=True)

nlp = spacy.load('en')

print('Processing the tokens...')
tic = time.time()
texts = []
for doc in data['text']:
    doc = nlp(doc)
    tokens = [tok.lemma_.lower().strip() for tok in doc if tok.lemma_ != '-PRON-']
    tokens = [tok for tok in tokens if tok not in ENGLISH_STOP_WORDS and tok not in string.punctuation]
    # TODO: add n-gram tokens
    tokens = ' '.join(tokens)
    texts.append(tokens)

toc = time.time()
print('Tokens had been done successfully. Cost: {:.2f} min'.format((toc - tic) / 60))

tic = time.time()
text_vec = csr_matrix(np.array([doc.vector for doc in nlp.pipe(texts, batch_size=500, n_threads=4)]))
toc = time.time()

print('Word vector had been trained successfully! Cost: {:.2f} min'.format((toc - tic) / 60))

# category dummy variable
dummy_var = ['cat1', 'cat2', 'has_brand', 'desc_has_price', 'shipping', 'item_condition_id']
x_dummies = csr_matrix(pd.get_dummies(data[dummy_var], sparse=True).values)

x = hstack((x_dummies, text_vec))

train_x = x[:ntrain]
test_x = x[ntrain:]

scipy.io.mmwrite(base_dir / 'data/train_x', train_x)
scipy.io.mmwrite(base_dir / 'data/test_x', test_x)
y.to_pickle(base_dir / 'data/train_y.pkl', y)
