#!/anaconda3/bin/python

"""
gp-net.py, SciML-SCD, RAL

A tool for inserting uncertainties into a neural network. 
"""
import argparse  
import sys
import logging
import os 
logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO"),
                    format="%(levelname)s:gp-net: %(message)s")
import numpy as np

from aux.get_info import megnet_input
from aux.activations import latent
from aux.plotting import plot
from train.MEGNetTrain import training
from optimizers.adam import adam 

VERSION = "1.0"

class Params:

    def __init__(self):
        """
        Params()
        
        Initialises the parameter list with default values. 
        These parameters can be changed by accessing these 
        class variables.
        """
        # General arguents
        self.checkdata = False
        self.ndims = 0
        
        # Specific to active learning 
        self.noactive = False
        self.repeat = False 
        self.samp = "entropy"
        self.cycle = 1, 5
        self.quan = 1000
        self.stop = 0.1 
        
        # For MEGNet only 
        self.nomeg = False 
        self.bond = 10
        self.nfeat = 2
        self.cutoff = 5
        self.width = 0.5
        self.include = False
        self.batch = 256
        self.prev = False
        self.layer = "readout_0"
        
        # For both MEGNet and GP
        self.epochs = 0
        self.frac = [0.3]
        self.nsplit = 1
        
        # For tSNE only 
        self.perp = 150
        self.niters = 1000
        
        # GP specific arguments
        self.rate = 0.01 
        self.amp = 1.0
        self.length = 1.0
        self.maxiters = [0]



def main():
    """ From command line, all parsing are handled here """
    parser = argparse.ArgumentParser(description="Uncertainty quantification in neural networks.")
    parser.add_argument("-checkdata", action="store_true",
                        help="Check number of entries in the dataset. [default: False]",
                        default = False)    
    parser.add_argument("-ltype", help="Display the layers in a fitted MEGNet model.",
                        type=str)
    parser.add_argument("-nomeg", action="store_true",
                        help="Do not train with MEGNet. [default: False]", default=False)

    parser.add_argument("-noactive", action="store_true",
                        help="Don't do active learning [default: False]", default=False)
    parser.add_argument("-samp", help="Type of sampling for active learning. Use random or\
                         entropy [default: entropy]", type=str)
    parser.add_argument("-cycle", help="Number of structures to sample and maximum number of times\
                        to sample separated by spaces for active learning. [default: 1 5]",
                        nargs=2, type=int)
    parser.add_argument("-repeat", action="store_true",
                        help="MEGNet train and pre-process activations in each active learning cycle\
                        [default: False]", default=False)
    parser.add_argument("-q", "--quan", help="Quantity of data for norepeat active learning\
                        [default: 1000]", type=int) 
    parser.add_argument("-stop", help="Minimum fraction of test set required for active learning\
                        [default: 0.1]", type=float)
    
    parser.add_argument("-data", 
                        help="Input dataset(s). Multiple datasets can be passed, one\
                        per optical property of interest. [No default]", type=str, nargs="+")
    parser.add_argument("-key", 
                        help="API key for data download and the optical properties of\
                        interest, separated by spaces. For MEGNet users only. [eg. Key band_gap\
                        formation_energy_per_atom e_above_hull]", type=str, nargs="+")
    parser.add_argument("-frac", 
                        help="Fraction of data for training and testing separated by spaces\
                        for train-test split and k-fold cross-validation. Fraction of data for\
                        training, and fraction of training data for validation in repeat active\
                        learning. For norepeat active learning, single input as the fraction of\
                        the training data for validation. [default: 0.3]", nargs="+", type=float)
    parser.add_argument("-include", action="store_true",
                        help="Include zero optical property values in the MEGNet training\
                        and/or Gaussian process analysis. [default: False]", default=False)
    parser.add_argument("-nsplit",
                        help="Number of training set splits for k-fold cross-validation.\
                        [default: 1 i.e no cross-validation]", type=int)
    
    parser.add_argument("-epochs", 
                        help="Epochs. [default: 0 ie. Perform no training with MEGNet]",
                        type=int)
    parser.add_argument("-batch",
                        help="Batch size for training with MEGNet or CNN. [default: 256]",
                        type=int)
    parser.add_argument("-bond", help="MEGNet feature bond. [default: 10]", type=int)
    parser.add_argument("-nfeat", help="MEGNet feature global. [default: 2]", type=int) 
    parser.add_argument("-cutoff", "--cutoff", help="MEGNet radial cutoff. [default: 5]",
                        type=int)
    parser.add_argument("-width", "--width", help="MEGNet gaussian width. [default: 0.5]",
                        type=float)    
    parser.add_argument("-prev", action="store_true",
                       help="Use a pre-trained MEGNet model during training with MEGNet.\
                       [default: False]", default=False)
    parser.add_argument("-layer",
                        help="MEGNet fitted model layer to analyse. [default: readout_0 i.e 32\
                        dense layer]", type=str)

    parser.add_argument("-ndims", 
                        help="Dimensions of embedded space. 0 => Do not preprocess activations\
                        , 1 => scale activations to 0, 1 range, 2 or 3 => Reduce dimensions of\
                        activations with tSNE. [default: 0]", type=int)
    parser.add_argument("-p", "--perp", 
                        help="Perplexity value to use in dimension reduction with tSNE.\
                        [default: 150]", type=float)
    parser.add_argument("-niters",
                        help="Number of iterations for optimisation in tSNE. [default: 1000]",
                        type=int)

    parser.add_argument("-rate", 
                        help="Adam optimizer Learning rate. [default: 0.01]", type=float)
    parser.add_argument("-amp", 
                        help="Amplitude of the GP kernel. [default: 1.0]", type=float)
    parser.add_argument("-length",
                        help="The length scale of the GP kernel. [default: 1.0]", type=float)
    parser.add_argument("-maxiters",
                        help="Maximum iterations for optimising GP hyperparameters. For\
                        k-fold cross-validation, two inputs are required - one for training\
                        per fold and the other for training using train-test split.\
                        \nFor active learning and train-test split, a single input\
                        is required. [default: 0 i.e no GP training]", nargs="+", type=int) 
    
    args = parser.parse_args()
    samp = args.samp or Params().samp
    cycle = args.cycle or Params().cycle
    quan = args.quan or Params().quan 
    stop = args.stop or Params().stop 
    fraction = args.frac or Params().frac
    nsplit = args.nsplit or Params().nsplit

    epochs = args.epochs or Params().epochs
    batch = args.batch or Params().batch
    bond = args.bond or Params().bond
    nfeat_global = args.nfeat or Params().nfeat
    cutoff = args.cutoff or Params().cutoff
    width = args.width or Params().width
    layer = args.layer or Params().layer

    ndims = args.ndims or Params().ndims    
    perp = args.perp or Params().perp
    niters = args.niters or Params().niters
    
    rate = args.rate or Params().rate 
    amp = args.amp or Params().amp
    length_scale = args.length or Params().length
    maxiters = args.maxiters or Params().maxiters


    # Display layers in a pre-fitted MEGNet model 
    if args.ltype:
        from aux.get_info import show_layers
        show_layers(args.ltype)
        sys.exit()

    if args.include:
        logging.info("Include zero optical property values ...")
    else:
        logging.info("Exclude zero optical property values ...")

    if args.nomeg: 
        logging.info("No MEGNet training requested ...")
        sys.exit("No other network implemented!")
    else:
        if epochs > 0:
            logging.info("MEGNet training requested...")
            if args.prev:
                logging.info("Use a pre-trained MEGNet model in MEGNet training ...")
            else:
                logging.info("Do not use a pre-trained MEGNet model in MEGNet training ...")

    if args.noactive:
        logging.info("No active learning requested ...")
        assert len(fraction) == 2, "-frac requires two inputs!"
        assert (fraction[0] + fraction[1]) == 1., "The sum of -frac must be 1!"
        if not (0 < (fraction[0] and fraction[1]) < 1): 
            logging.error("-frac must be of the form 0 < parameter < 1!")
            sys.exit()
        if nsplit == 1:
            logging.info("Train-test split approach requested ...")
            assert len(maxiters) == 1, "-maxiters must have length 1!"
            maxiters = maxiters[0]
        else:
            print("%s-fold cross-validation requested ..." %nsplit)
            assert len(maxiters) == 2, "-maxiters must have length 2!"
    else:
        logging.info("Perform active learning ...")
        assert stop < 1., "Stop argument should be less than 1!"
        assert nsplit == 1, "Active learning with k-fold cross validation not supported!"
        assert len(maxiters) == 1, "-maxiters must have length 1!"
        maxiters = maxiters[0]
        if samp not in ("entropy", "random"):
            logging.error("Sampling type not recognised!")
            sys.exit()
            
        if args.repeat:
            logging.info("MEGNet train and perform activation analysis per cycle of active learning ...")
            assert len(fraction) == 2, "-frac requires two inputs!"
            assert (fraction[0] + fraction[1]) < 1., "The sum of -frac must be less than 1!"
            if not (0 < (fraction[0] and fraction[1]) < 1):
                logging.error("-frac must be of the form 0 < parameter < 1!")
                sys.exit()
        else:
            logging.info("MEGNet train and perform activation analysis ONCE during the active learning ...")
            assert len(fraction) == 1, "-frac requires a single input as the validation fraction!"
            assert fraction[0] < 1., "-frac must be less than 1!" #fraction is a list and we need to pass a single input 
            if not quan:
                logging.error("Provide quantity of data to use with -q or --quan!")
                sys.exit()

            
    # Get data for processing 
    if args.data or (args.data and args.key):
        from aux.get_info import load_data
        properties = load_data(args.data)
    elif args.key:
        from aux.get_info import download
        properties = download(args.key)
    else:
        logging.error("No input data provided. Use -data or -key option!")
        sys.exit()

    # Check number of entries in dataset
    if args.checkdata:
        from aux.get_info import ReadData
        for prop in properties:
            for dat in args.data:
                ReadData(dat, args.include)
        sys.exit()    

    for prop in properties:
        if args.noactive:
            if not args.nomeg:
                model, activations_input_full, Xfull, yfull, Xpool, ypool, Xtest, ytest =\
                    megnet_input(prop, args.include, bond, nfeat_global, cutoff, width, fraction)
            
            if nsplit == 1:
                #*****************************
                # TRAIN-TEST SPLIT APPROACH 
                #*****************************
                datadir = "train_test_split/%s_results" %prop

                if not args.nomeg and epochs > 0:
                    logging.info("Training MEGNet on the pool ...")
                    training.train_test_split(datadir, prop, args.prev, model, batch,
                                              epochs, Xpool, ypool, Xtest, ytest)
                    
                logging.info("Obtaining latent points for the full dataset ...")
                latent_pool, latent_test = latent.train_test_split(
                    datadir, prop, layer, activations_input_full, Xpool, ytest, perp,
                    ndims, niters)
            
                logging.info("Gaussian Process initiated ...")
                OptLoss, OptAmp, OptLength, Optmae, Optmse, Optsae, gp_mean, gp_stddev, R =\
                    adam.train_test_split(datadir, prop, latent_pool, latent_test, ypool, ytest,
                                          maxiters, amp, length_scale, rate)

                logging.info("Saving optimised hyperparameters and GP posterior plots ...")
                plot.train_test_split(datadir, prop, layer, maxiters, rate, OptLoss, OptAmp,
                                      OptLength, ytest, gp_mean, gp_stddev, None, None, Optmae,
                                      Optmse, Optsae, R)
                
            elif nsplit > 1:
                #***************************
                # K-FOLD CROSS VALIDATION
                #***************************
                from sklearn.model_selection import KFold

                OptAmp_fold = np.array([])
                OptLength_fold = np.array([])
                Optmae_val_fold = np.array([])
                Optmse_val_fold = np.array([])
                mae_test_fold = np.array([])
                kf = KFold(n_splits=nsplit, shuffle=True, random_state=0)
                for fold, (train_idx, val_idx) in enumerate(kf.split(Xpool)):
                    datadir = "k_fold/%s_results/0%s_fold" %(prop, fold)
                    Xtrain, Xval = Xpool[train_idx], Xpool[val_idx]
                    ytrain, yval = ypool[train_idx], ypool[val_idx]

                    if not args.nomeg and epochs > 0:
                        print("\nTraining MEGNet on fold %s training set ..." %fold)
                        training.k_fold(datadir, fold, prop, args.prev, model, batch, epochs,
                                        Xtrain, ytrain, Xval, yval)

                    logging.info("Obtaining latent points for the full dataset ...")
                    latent_train, latent_val, latent_test = latent.k_fold(
                        datadir, fold, prop, layer, activations_input_full, train_idx, val_idx,
                        Xpool, perp, ndims, niters)

                    logging.info("Gaussian Process initiated ...")
                    amp, length_scale, Optmae_val, Optmse_val, mae_test = adam.k_fold(
                        datadir, prop, latent_train, latent_val, latent_test, ytrain, yval, ytest,
                        maxiters[0], amp, length_scale, rate)
                    OptAmp_fold = np.append(OptAmp_fold, amp) 
                    OptLength_fold = np.append(OptLength_fold, length_scale)
                    Optmae_val_fold = np.append(Optmae_val_fold, Optmae_val)
                    Optmse_val_fold = np.append(Optmse_val_fold, Optmse_val)
                    mae_test_fold = np.append(mae_test_fold, mae_test)
                if all(Optmae_val_fold): 
                    print("\nCross-validation statistics: MAE = %.4f, MSE = %.4f" %(
                        Optmae_val_fold.mean(), Optmse_val_fold.mean()))
                logging.info("Cross-validation complete!")

                print("")
                # Choose the best fitted model for the train-test split training             
                logging.info("Training MEGNet on the pool ...")
                if args.prev: 
                    prev = "k_fold/%s_results/0%s_fold/model-best-new-%s.h5" %(
                        prop, np.argmin(Optmae_val_fold), prop)
                    print("The selected best fitted model: %s" %prev)
                    args.prev = prev 
                datadir = "k_fold/%s_results" %prop
                if not args.nomeg and epochs > 0:
                    training.train_test_split(datadir, prop, args.prev, model, batch, epochs,
                                              Xpool, ypool, Xtest, ytest)
                    
                logging.info("Obtaining latent points for the full dataset ...")
                latent_pool, latent_test = latent.train_test_split(
                    datadir, prop, layer, activations_input_full, Xpool, ytest, perp, ndims, niters)
                
                logging.info("Gaussian Process initiated ...")
                OptLoss, OptAmp, OptLength, Optmae, Optmse, Optsae, gp_mean, gp_stddev, R =\
                    adam.train_test_split(datadir, prop, latent_pool, latent_test, ypool, ytest,
                                          maxiters[1], amp, length_scale, rate)

                logging.info("Saving optimised hyperparameters and GP posterior plots ...")
                plot.train_test_split(datadir, prop, layer, maxiters[1], rate, OptLoss, OptAmp,
                                      OptLength, ytest, gp_mean, gp_stddev, Optmae_val_fold,
                                      mae_test_fold, Optmae, Optmse, Optsae, R)
        else:
             import subprocess
             from aux.pool_sampling import selection_fn
             EntropySelection = selection_fn.EntropySelection
             RandomSelection = selection_fn.RandomSelection

             query = cycle[0]
             max_query = cycle[1]
             print("Number of cycle(s): ", max_query)
             print("Number of samples to move per cycle: ", query)

             if args.repeat:
                 #********************************************
                 # ACTIVE LEARNING WITH CYCLES OF NETWORK 
                 # TRAINING AND ACTIVATION EXTRACTION ANALYSIS
                 #********************************************
                 training_data = np.array([])
                 Optmae_val_cycle = np.array([])
                 mae_test_cycle = np.array([])
                 mse_test_cycle = np.array([])
                 sae_test_cycle = np.array([])             
                 
                 if not args.nomeg:
                     (model, activations_input_full, Xfull, yfull, Xpool, ypool, Xtest,
                      ytest, Xtrain, ytrain, Xval, yval) = megnet_input(
                          prop, args.include, bond, nfeat_global, cutoff, width, fraction)
                     
                 # Ensure there is adequate data in test set before proceeding
                 assert (query * max_query) < int(stop * len(ytest)),\
                     "Test set size should be at least %s%% the dataset after active learning. Reduce stop and/or cycle parameters!" %stop                     

                 for i in range(max_query+1):
                     print("\nQuery number ", i)
                     datadir = "active_learn/repeat/%s_results/%s/0%s_model" %(prop, samp, i)

                     if not args.nomeg and epochs > 0:
                         logging.info("Training MEGNet on the pool ...")
                         training.active(datadir, i, prop, args.prev, model, samp,
                                         batch, epochs, Xpool, ypool, Xtest, ytest)
                         
                     logging.info("Obtaining latent points for the full dataset ...")
                     latent_train, latent_val, latent_test = latent.active(
                         datadir, prop, layer, samp, activations_input_full, Xfull, Xtest,
                         ytest, Xtrain, Xval, perp, ndims, niters)

                     logging.info("Gaussian Process initiated ...")
                     (OptLoss, OptAmp, OptLength, amp, length_scale, gp_mean, gp_stddev,
                      gp_variance, Optmae_val, mae_test, mse_test, sae_test, R) =\
                          adam.active(datadir, prop, latent_train, latent_val, latent_test,
                                      ytrain, yval, ytest, maxiters, amp, length_scale, rate)
                     
                     # Save some parameters for plotting purposes.
                     training_data = np.append(training_data, len(ytrain)) 
                     Optmae_val_cycle = np.append(Optmae_val_cycle, Optmae_val)
                     mae_test_cycle = np.append(mae_test_cycle, mae_test)
                     mse_test_cycle = np.append(mse_test_cycle, mse_test)
                     sae_test_cycle = np.append(sae_test_cycle, sae_test)

                     logging.info("Saving optimised hyperparameters and GP posterior plots ...")
                     plot.active(datadir, prop, layer, maxiters, rate, OptLoss, OptAmp, OptLength,
                                 samp, query, training_data, ytest, gp_mean, gp_stddev,
                                 Optmae_val_cycle, mae_test_cycle, mae_test, mse_test, sae_test, R)

                     # Sample using variance on the predictions 
                     if i < max_query:
                         if samp == "entropy":
                             if i == 0:
                                 logging.info("Entropy sampling for active learning enabled ...")
                             Xpool, ypool, Xtrain, ytrain, Xtest, ytest = EntropySelection(
                                 i, Xtrain, ytrain, Xtest, ytest, Xval, yval, gp_variance, query, max_query)
                         elif samp == "random":
                             if	i == 0:
                                 logging.info("Random sampling for active learning enabled ...")
                             Xpool, ypool, Xtrain, ytrain, Xtest, ytest = RandomSelection(
                                 i, Xtrain, ytrain, Xtest, ytest, Xval, yval, gp_variance, query, max_query)
                     elif i == max_query:
                         if os.path.isdir("callback/"):
                             subprocess.call(["rm", "-r", "callback"])
                             
             else:
                 import matplotlib
                 matplotlib.use("agg")
                 import matplotlib.pyplot as plt
                 #************************************
                 # ACTIVE LEARNING WITHOUT CYCLES OF
                 # NETWORK TRAINING AND tSNE ANALYSIS
                 #*************************************
                 val_frac = fraction[0]
                 training_data = np.array([]) 
                 Optmae_val_cycle = np.array([])
                 mae_test_cycle = np.array([]) 
                 mse_test_cycle = np.array([]) 
                 sae_test_cycle = np.array([])
                 samp_idx = np.array([])
                 
                 if not args.nomeg:
                     model, activations_input_full, Xfull, yfull =\
                         megnet_input(prop, args.include, bond, nfeat_global, cutoff, width,
                                      fraction, quan)

                 datadir = "active_learn/norepeat/%s_results/%s_model" %(prop, quan)
                 if not os.path.isdir(datadir):
                     os.makedirs(datadir)
                         
                 Xpool = Xfull[:quan]
                 ypool = yfull[:quan]
                 Xtest = Xfull[quan:]
                 ytest = yfull[quan:]

                 # Ensure there is adequate data in test set before proceeding
                 assert (query * max_query) < int(stop * len(ytest)),\
                     "Test set size should be at least %s%% the dataset after active learning. Reduce stop and/or cycle parameters!" %stop
                     
                 val_boundary = int(len(Xpool) * val_frac)
                 Xtrain = Xpool[:-val_boundary]
                 ytrain = ypool[:-val_boundary]
                 Xval = Xpool[-val_boundary:]
                 yval = ypool[-val_boundary:]

                 print("Requested validation set: %s%% of pool" %(val_frac*100))
                 print("Training set:", ytrain.shape)
                 print("Validation set:", yval.shape)
                 print("Test set:", ytest.shape)

                 logging.info("Saving the data to file ...")
                 np.save("%s/ytrain.npy" %datadir, ytrain)
                 np.save("%s/yval.npy" %datadir, yval)

                 print("\nProcessing %s samples ..." %quan)
                 # MEGNet train and tSNE analyse or scale features once 
                 if not args.nomeg and epochs > 0:
                     training.train_test_split(datadir, prop, args.prev, model, batch,
                                               epochs, Xpool, ypool, Xtest, ytest)
                     
                 logging.info("Obtaining latent points for the full dataset ...")
                 latent.active(datadir, prop, layer, samp, activations_input_full,
                               Xfull, Xtest, ytest, Xtrain, Xval, perp, ndims, niters)
                     
                 logging.info("Loading the latent points ...")
                 latent_train = np.load("%s/latent_train.npy" %datadir)
                 latent_test = np.load("%s/latent_test.npy" %datadir)
                 latent_val = np.load("%s/latent_val.npy" %datadir)

                 # Lets create a new data directory and dump GP results into it 
                 datadir = datadir + "/" + samp + "/%s_samples" %query
                 if not os.path.isdir(datadir):
                     os.makedirs(datadir)
                         
                 for i in range(max_query+1):
                     print("\nQuery number ", i)

                     # Run the Gaussian Process
                     # GP train only at query 0 for the best hyperparameters
                     # required for the subsequent queries 
                     if i == 0:
                         (OptLoss, OptAmp, OptLength, amp, length_scale, gp_mean, gp_stddev,
                          gp_variance, Optmae_val, mae_test, mse_test, sae_test, R) =\
                              adam.active(datadir, prop, latent_train, latent_val, latent_test,
                                          ytrain, yval, ytest, maxiters, amp, length_scale, rate)
                     else: 
                         maxiters = 0
                         (OptLoss, OptAmp, OptLength, Amp, Length_Scale, gp_mean, gp_stddev,
                          gp_variance, Optmae_val, mae_test, mse_test, sae_test, R) =\
                              adam.active(datadir, prop, latent_train, latent_val, latent_test,
                                          ytrain, yval, ytest, maxiters, amp, length_scale, rate)
                         # Set the new hyperparameters to those from query 0 
                         Amp = amp
                         Length_Scale = length_scale 

                     # Dump some parameters to an array for plotting purposes.
                     training_data = np.append(training_data, len(ytrain)) 
                     mae_test_cycle = np.append(mae_test_cycle, mae_test) 
                     mse_test_cycle = np.append(mse_test_cycle, mse_test) 
                     sae_test_cycle = np.append(sae_test_cycle, sae_test) 
                     if maxiters > 0:
                         Optmae_val_cycle = np.append(Optmae_val_cycle, Optmae_val) 

                     if i < max_query: 
                         if samp == "entropy":
                             if i == 0:
                                 logging.info("Entropy sampling for active learning enabled ...")
                             idx, latent_pool, ypool, latent_train, ytrain, latent_test, ytest  =\
                                 EntropySelection(i, latent_train, ytrain, latent_test, ytest,
                                                  latent_val, yval, gp_variance, query, max_query)
                         elif samp == "random":
                             if i == 0:
                                 logging.info("Random sampling for active learning enabled ...")
                             idx, latent_pool, ypool, latent_train, ytrain, latent_test, ytest  =\
                                 RandomSelection(i, latent_train, ytrain, latent_test, ytest,
                                                 latent_val, yval, gp_variance, query, max_query)
                         samp_idx = np.append(samp_idx, idx)
                                 
                 logging.info("Writing the results to file ...")
                 np.save("%s/training_data_for_plotting.npy" %datadir, training_data)
                 np.save("%s/gp_mae.npy" %datadir, mae_test_cycle)
                 np.save("%s/gp_mse.npy" %datadir, mse_test_cycle)
                 np.save("%s/gp_sae.npy" %datadir, sae_test_cycle)
                 np.save("%s/samp_indices.npy" %datadir, samp_idx)
                 np.save("%s/Xtest.npy" %datadir, np.delete(Xtest, samp_idx))                 
                 if maxiters > 0:
                     np.save("%s/val_mae.npy" %datadir, Optmae_val_cycle)

                 logging.info("Saving plots ...")
                 plot.norepeat(datadir, prop, layer, samp, query, maxiters)


                 
if __name__ == "__main__":
    print ("\ngp-net.py ver ", VERSION)
    main()
