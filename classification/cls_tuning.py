import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.feature_selection import SelectKBest, f_classif, mutual_info_classif
from sklearn.model_selection import GridSearchCV
from sklearn.metrics import recall_score


def summary_tuning(cname, grid_result, filename):
    """
    Summarize results of cross-validation on set A for hyperparameter tuning

    Inputs:
    - cname: classifier name
    - grid_result: gridsearch results for this classifier, output of grid.fit(AX, Ay)
    - filename: filename with path to write the summary to
    """
    means = grid_result.cv_results_['mean_test_score']
    stds = grid_result.cv_results_['std_test_score']
    params = grid_result.cv_results_['params']

    # print best result and append to our lists
    print("%r -> Best cross-val score on A set: %f using %s" % (cname, grid_result.best_score_, grid_result.best_params_))

    # dataframe with summary
    d = {
        'model': cname,
        'mean_acc_A': means,
        'stdev_acc_A': stds,
        'params': params,
    }
    df = pd.DataFrame(data = d)
    df.to_csv(filename, index=False)


def hp_tuner(AX, BX, Ay, By, get_cls_functions, feats_names):
    """
    Perform nested hyperparameter tuning.
    Given training data splitted into A, B sets and for each classifier type:
    Stratified cross-validation for feature selection and hyperparameter tuning using set A
    Generates csv file with summary of hp tuning (set A)
    Evaluate the performance on set B and return accs

    Input:
    - AX and BX: features of the train set, splitted
    - Ay and By: labels of the train set, splitted
    - get_cls_functions: list of functions tho get classifier and dict of hp to tune

    Output:
    - cls_acc_hps: pandas dataframe with:
        - classifiers names
        - classifiers hyperparameters
        - selected features
        - accuracies on B set
        of each tuned classifier corresponding to get_cls_functions
    - trained_cls_list: list of classifiers tuned and trained on (AX+BX)
    """

    # init lists (there will be one element per classifier in get_cls_functions)

    classifiers_names = []
    classifiers = []
    hparam_grids = []
    best_accs = [] # on the B set
    best_hps = [] # determined with CV on A
    sel_feats_i = [] # indexes of selected features
    sel_feats = [] # names of selected features
    trained_cls_list = [] # tuned classifier trained on X,y

    # iterate over list of functions
    # to get classifiers and parameters and append to our lists

    for fn in get_cls_functions:
        clsname, cls, hp = fn()
        classifiers_names.append(clsname)
        classifiers.append(cls)
        hparam_grids.append(hp)

    # tune hyperparameters with GridSearchCV for each classifier

    for i in np.arange(len(classifiers)):

        # create pipeline
        pipe = Pipeline([
            ('selecter', SelectKBest(f_classif, k=4)),
            ('classifier', classifiers[i])
        ])

        # feature selection params
        fsel_params = dict(
            selecter__k = np.arange(2, AX.shape[1], 5)
        )

        # feature selection params and classifier's params for param_grid:
        all_params = {**fsel_params, **hparam_grids[i]}

        # perform grid search
        grid = GridSearchCV(estimator=pipe,
                            param_grid=all_params,
                            scoring='recall_macro', # average per-class accuracy
                            n_jobs=1,
                            cv=10)

        # This might take a while:
        grid_result = grid.fit(AX, Ay)

        # summary of hp tuning on set A
        # generate one csv file per classifier
        summary_tuning(classifiers_names[i],
                       grid_result,
                       r'.\data_while_tuning\%s_tuning.csv' % classifiers_names[i])

        # get selected features on set A
        sel_i = grid_result.best_estimator_.named_steps['selecter'].get_support()
        selected = [i for indx, i in enumerate(feats_names) if sel_i[indx]]
        print("%r -> Selected features: %r" % (classifiers_names[i], selected))
        sel_feats_i.append(sel_i)
        sel_feats.append(selected)

        # evaluate classifier on set B
        By_pred = grid_result.best_estimator_.predict(BX)
        score_on_B = recall_score(By, By_pred, average='macro')
        print("%r -> Average per-class accuracy on B set: %f\n" % (classifiers_names[i], score_on_B))

        # add score on B and hyperparams for output
        best_accs.append(score_on_B)
        best_hps.append(grid_result.best_params_)

        # train classifier using all training data with this classifier
        X = np.concatenate((AX, BX), axis=0)
        y = np.concatenate((Ay, By), axis=0)
        trained_cls = grid_result.best_estimator_.fit(X,y)
        trained_cls_list.append(trained_cls)

    # create the output dataframe
    d = {
        'classifiers_names': classifiers_names,
        'best_accs': best_accs,
        'best_hps': best_hps,
        'sel_feats': sel_feats,
        'sel_feats_i': sel_feats_i
    }
    cls_acc_hps = pd.DataFrame(data = d)

    return cls_acc_hps, trained_cls_list


def save_tuning(tuning_all, trained_all):
    """
    Saving outpus of hp tuning to disk
    Called after tuning each classifier

    Input:
    - tuning_all: pandas df with tuning results
    - trained_all: list of all classifiers trained on training data
    """

    # save tuning_all
    tuning_all.to_csv(r'.\data_while_tuning\tuning_all.csv', index=False)

    # save trained_all
    for i in np.arange(len(trained_all)):
        filename = r'.\data_while_tuning\trained_' + tuning_all.loc[i, 'classifiers_names'] + '.sav'
        pickle.dump(trained_all[i], open(filename, 'wb'))


def load_tuning():
    """
    Loading outpus of hp tuning from disk
    Called to recover what was tuned and trained in previous sessions

    Output:
    - tuning_all: pandas df with tuning results
    - trained_all: list of all classifiers trained on training data
    """

    # load tuning_all
    tuning_all = pd.read_csv(r'.\data_while_tuning\tuning_all.csv')

    # load trained_all
    trained_all=[]
    for i in np.arange(len(tuning_all)):
        filename = r'.\data_while_tuning\trained_' + tuning_all.loc[i, 'classifiers_names'] + '.sav'
        loaded_model = pickle.load(open(filename, 'rb'))
        trained_all.append(loaded_model)

    return tuning_all, trained_all