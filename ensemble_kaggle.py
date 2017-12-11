# -*- coding: utf-8 -*-

import gc
import time
import numpy as np
import pandas as pd

from scipy.sparse import csr_matrix, hstack

from sklearn.linear_model import Ridge
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.preprocessing import LabelBinarizer
from sklearn.model_selection import train_test_split, cross_val_score
import lightgbm as lgb

NUM_BRANDS = 4000
NUM_CATEGORIES = 1000
NAME_MIN_DF = 10
MAX_FEATURES_ITEM_DESCRIPTION = 50000


def handle_missing_inplace(dataset):
    dataset['category_name'].fillna(value='missing', inplace=True)
    dataset['brand_name'].fillna(value='missing', inplace=True)
    dataset['item_description'].fillna(value='missing', inplace=True)


def cutting(dataset):
    pop_brand = dataset['brand_name'].value_counts().loc[lambda x: x.index != 'missing'].index[:NUM_BRANDS]
    dataset.loc[~dataset['brand_name'].isin(pop_brand), 'brand_name'] = 'missing'
    pop_category = dataset['category_name'].value_counts().loc[lambda x: x.index != 'missing'].index[:NUM_CATEGORIES]
    dataset.loc[~dataset['category_name'].isin(pop_category), 'category_name'] = 'missing'


def to_categorical(dataset):
    dataset['category_name'] = dataset['category_name'].astype('category')
    dataset['brand_name'] = dataset['brand_name'].astype('category')
    dataset['item_condition_id'] = dataset['item_condition_id'].astype('category')


def main():
    start_time = time.time()

    train = pd.read_table('./data/train.tsv', engine='c')
    test = pd.read_table('./data/test.tsv', engine='c')
    print('[{}] Finished to load data'.format(time.time() - start_time))
    print('Train shape: ', train.shape)
    print('Test shape: ', test.shape)

    nrow_train = train.shape[0]
    y = np.log1p(train["price"])
    merge: pd.DataFrame = pd.concat([train, test])
    submission: pd.DataFrame = test[['test_id']]

    del train
    del test
    gc.collect()

    handle_missing_inplace(merge)
    print('[{}] Finished to handle missing'.format(time.time() - start_time))

    cutting(merge)
    print('[{}] Finished to cut'.format(time.time() - start_time))

    to_categorical(merge)
    print('[{}] Finished to convert categorical'.format(time.time() - start_time))

    cv = CountVectorizer(min_df=NAME_MIN_DF)
    X_name = cv.fit_transform(merge['name'])
    print('[{}] Finished count vectorize `name`'.format(time.time() - start_time))

    cv = CountVectorizer()
    X_category = cv.fit_transform(merge['category_name'])
    print('[{}] Finished count vectorize `category_name`'.format(time.time() - start_time))

    tv = TfidfVectorizer(max_features=MAX_FEATURES_ITEM_DESCRIPTION,
                         ngram_range=(1, 3),
                         stop_words='english')
    X_description = tv.fit_transform(merge['item_description'])
    print('[{}] Finished TFIDF vectorize `item_description`'.format(time.time() - start_time))

    lb = LabelBinarizer(sparse_output=True)
    X_brand = lb.fit_transform(merge['brand_name'])
    print('[{}] Finished label binarize `brand_name`'.format(time.time() - start_time))

    X_dummies = csr_matrix(pd.get_dummies(merge[['item_condition_id', 'shipping']],
                                          sparse=True).values)
    print('[{}] Finished to get dummies on `item_condition_id` and `shipping`'.format(time.time() - start_time))

    sparse_merge = hstack((X_dummies, X_description, X_brand, X_category, X_name)).tocsr()
    print('[{}] Finished to create sparse merge'.format(time.time() - start_time))

    X = sparse_merge[:nrow_train]
    X_test = sparse_merge[nrow_train:]

    model = Ridge(solver="sag", fit_intercept=False, random_state=666, alpha=1.25)
    model.fit(X, y)
    print('[{}] Finished to train ridge sag'.format(time.time() - start_time))
    predsR = model.predict(X=X_test)
    print('[{}] Finished to predict ridge sag'.format(time.time() - start_time))

    model = Ridge(solver="lsqr", fit_intercept=False, random_state=666, alpha=1.25)
    model.fit(X, y)
    print('[{}] Finished to train ridge lsqrt'.format(time.time() - start_time))
    predsR2 = model.predict(X=X_test)
    print('[{}] Finished to predict ridge lsqrt'.format(time.time() - start_time))

    model = Ridge(solver="sag", fit_intercept=True, random_state=666, alpha=1.25)
    model.fit(X, y)
    print('[{}] Finished to train ridge sag'.format(time.time() - start_time))
    predsR3 = model.predict(X=X_test)
    print('[{}] Finished to predict ridge sag'.format(time.time() - start_time))

    train_X, valid_X, train_y, valid_y = train_test_split(X, y, test_size=0.15, random_state=666)
    d_train = lgb.Dataset(train_X, label=train_y, max_bin=8192)
    d_valid = lgb.Dataset(valid_X, label=valid_y, max_bin=8192)
    watchlist = [d_train, d_valid]

    params = {
        'learning_rate': 0.715,
        'application': 'regression',
        'max_depth': 3,
        'num_leaves': 110,
        'verbosity': -1,
        'metric': 'RMSE',
        'nthread': 4
    }

    params2 = {
        'learning_rate': 0.815,
        'application': 'regression',
        'max_depth': 3,
        'num_leaves': 90,
        'verbosity': -1,
        'metric': 'RMSE',
        'nthread': 4
    }

    model = lgb.train(params, train_set=d_train, num_boost_round=7500, valid_sets=watchlist,
                      early_stopping_rounds=500, verbose_eval=500)
    predsL = model.predict(X_test)

    print('[{}] Finished to predict lgb 1'.format(time.time() - start_time))

    train_X2, valid_X2, train_y2, valid_y2 = train_test_split(X, y, test_size=0.15, random_state=666)
    d_train2 = lgb.Dataset(train_X2, label=train_y2, max_bin=8192)
    d_valid2 = lgb.Dataset(valid_X2, label=valid_y2, max_bin=8192)
    watchlist2 = [d_train2, d_valid2]

    model = lgb.train(params2, train_set=d_train2, num_boost_round=3000, valid_sets=watchlist2,
                      early_stopping_rounds=50, verbose_eval=500)
    predsL2 = model.predict(X_test)

    print('[{}] Finished to predict lgb 2'.format(time.time() - start_time))

    preds = predsR3 * 0.05 + predsR2 * 0.05 + predsR * 0.16 + predsL * 0.5 + predsL2 * 0.24

    submission['price'] = np.expm1(preds)
    submission.to_csv("./data/submission_lgbm_ridge_1.csv", index=False)


if __name__ == '__main__':
    main()
