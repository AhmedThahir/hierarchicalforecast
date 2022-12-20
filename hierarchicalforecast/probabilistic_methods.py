# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/probabilistic_methods.ipynb.

# %% auto 0
__all__ = ['Normality']

# %% ../nbs/probabilistic_methods.ipynb 3
from typing import Dict

import numpy as np
from scipy.stats import norm
from sklearn.preprocessing import OneHotEncoder

from .utils import is_strictly_hierarchical, cov2corr

# %% ../nbs/probabilistic_methods.ipynb 6
class Normality:
    """ Normality Probabilistic Reconciliation Class.

    The Normality method leverages the Gaussian Distribution linearity, to
    generate hierarchically coherent prediction distributions. This class is 
    meant to be used as the `sampler` input as other `HierarchicalForecast` [reconciliation classes](https://nixtla.github.io/hierarchicalforecast/methods.html).

    Given base forecasts under a normal distribution:
    $$\hat{y}_{h} \sim \mathrm{N}(\hat{\\boldsymbol{\\mu}}, \hat{\mathbf{W}}_{h})$$

    The reconciled forecasts are also normally distributed:
    $$\\tilde{y}_{h} \sim \mathrm{N}(\mathbf{S}\mathbf{P}\hat{\\boldsymbol{\\mu}}, 
    \mathbf{S}\mathbf{P}\hat{\mathbf{W}}_{h} \mathbf{P}^{\intercal} \mathbf{S}^{\intercal})$$

    **Parameters:**<br>
    `S`: np.array, summing matrix of size (`base`, `bottom`).<br>
    `P`: np.array, reconciliation matrix of size (`bottom`, `base`).<br>
    `y_hat`: Point forecasts values of size (`base`, `horizon`).<br>
    `W`: np.array, hierarchical covariance matrix of size (`base`, `base`).<br>
    `sigmah`: np.array, forecast standard dev. of size (`base`, `horizon`).<br>
    `num_samples`: int, number of bootstraped samples generated.<br>
    `seed`: int, random seed for numpy generator's replicability.<br>    

    **References:**<br>
    - [Panagiotelis A., Gamakumara P. Athanasopoulos G., and Hyndman R. J. (2022).
    "Probabilistic forecast reconciliation: Properties, evaluation and score optimisation". European Journal of Operational Research.](https://www.sciencedirect.com/science/article/pii/S0377221722006087)
    """
    def __init__(self,
                 S: np.ndarray,
                 P: np.ndarray,
                 y_hat: np.ndarray,
                 sigmah: np.ndarray,
                 W: np.ndarray,
                 seed: int = 0):
        self.S = S
        self.P = P
        self.y_hat = y_hat
        self.SP = self.S @ self.P
        self.W = W
        self.sigmah = sigmah
        self.seed = seed

        # Base Normality Errors assume independence/diagonal covariance
        # TODO: replace bilinearity with elementwise row multiplication
        R1 = cov2corr(self.W)
        Wh = [np.diag(sigma) @ R1 @ np.diag(sigma).T for sigma in self.sigmah.T]

        # Reconciled covariances across forecast horizon
        self.cov_rec = [(self.SP @ W @ self.SP.T) for W in Wh]
        self.sigmah_rec = np.hstack([np.sqrt(np.diag(cov))[:, None] for cov in self.cov_rec])

    def get_samples(self, num_samples: int=None):
        """Normality Coherent Samples.

        Obtains coherent samples under the Normality assumptions.

        **Parameters:**<br>
        `num_samples`: int, number of samples generated from coherent distribution.<br>

        **Returns:**<br>
        `samples`: Coherent samples of size (`base`, `horizon`, `num_samples`).
        """
        state = np.random.RandomState(self.seed)
        n_series, n_horizon = self.y_hat.shape
        samples = np.empty(shape=(num_samples, n_series, n_horizon))
        for t in range(n_horizon):
            partial_samples = state.multivariate_normal(mean=self.SP @ self.y_hat[:,t],
                                                  cov=self.cov_rec[t], size=num_samples)
            samples[:,:,t] = partial_samples

        # [samples, N, H] -> [N, H, samples]
        samples = samples.transpose((1, 2, 0))
        return samples

    def get_prediction_levels(self, res, level):
        """ Adds reconciled forecast levels to results dictionary """
        res['sigmah'] = self.sigmah_rec
        level = np.asarray(level)
        z = norm.ppf(0.5 + level / 200)
        for zs, lv in zip(z, level):
            res[f'lo-{lv}'] = res['mean'] - zs * self.sigmah_rec
            res[f'hi-{lv}'] = res['mean'] + zs * self.sigmah_rec
        return res

    def get_prediction_quantiles(self, res, quantiles):
        """ Adds reconciled forecast quantiles to results dictionary """
        # [N,H,None] + [None None,Q] * [N,H,None] -> [N,H,Q]
        z = norm.ppf(quantiles)
        res['sigmah'] = self.sigmah_rec
        res['quantiles'] = res['mean'][:,:,None] + z[None,None,:] * self.sigmah_rec[:,:,None]
        return res

# %% ../nbs/probabilistic_methods.ipynb 10
class Bootstrap:
    """ Bootstrap Probabilistic Reconciliation Class.

    This method goes beyond the normality assumption for the base forecasts,
    the technique simulates future sample paths and uses them to generate
    base sample paths that are latered reconciled. This clever idea and its
    simplicity allows to generate coherent bootstraped prediction intervals
    for any reconciliation strategy. This class is meant to be used as the `sampler` 
    input as other `HierarchicalForecast` [reconciliation classes](https://nixtla.github.io/hierarchicalforecast/methods.html).

    Given a boostraped set of simulated sample paths:
    $$(\hat{\mathbf{y}}^{[1]}_{\\tau}, \dots ,\hat{\mathbf{y}}^{[B]}_{\\tau})$$

    The reconciled sample paths allow for reconciled distributional forecasts:
    $$(\mathbf{S}\mathbf{P}\hat{\mathbf{y}}^{[1]}_{\\tau}, \dots ,\mathbf{S}\mathbf{P}\hat{\mathbf{y}}^{[B]}_{\\tau})$$

    **Parameters:**<br>
    `S`: np.array, summing matrix of size (`base`, `bottom`).<br>
    `P`: np.array, reconciliation matrix of size (`bottom`, `base`).<br>
    `y_hat`: Point forecasts values of size (`base`, `horizon`).<br>
    `y_insample`: Insample values of size (`base`, `insample_size`).<br>
    `y_hat_insample`: Insample point forecasts of size (`base`, `insample_size`).<br>
    `num_samples`: int, number of bootstraped samples generated.<br>
    `seed`: int, random seed for numpy generator's replicability.<br>

    **References:**<br>
    - [Puwasala Gamakumara Ph. D. dissertation. Monash University, Econometrics and Business Statistics (2020).
    "Probabilistic Forecast Reconciliation"](https://bridges.monash.edu/articles/thesis/Probabilistic_Forecast_Reconciliation_Theory_and_Applications/11869533)
    - [Panagiotelis A., Gamakumara P. Athanasopoulos G., and Hyndman R. J. (2022).
    "Probabilistic forecast reconciliation: Properties, evaluation and score optimisation". European Journal of Operational Research.](https://www.sciencedirect.com/science/article/pii/S0377221722006087)
    """
    def __init__(self,
                 S: np.ndarray,
                 P: np.ndarray,
                 y_hat: np.ndarray,
                 y_insample: np.ndarray,
                 y_hat_insample: np.ndarray,
                 num_samples: int=100,
                 seed: int = 0,
                 W: np.ndarray = None):
        self.S = S
        self.P = P
        self.W = W
        self.y_hat = y_hat
        self.y_insample = y_insample
        self.y_hat_insample = y_hat_insample
        self.num_samples = num_samples
        self.seed = seed

    def get_samples(self, num_samples: int=None):
        """Bootstrap Sample Reconciliation Method.

        Applies Bootstrap sample reconciliation method as defined by Gamakumara 2020.
        Generating independent sample paths and reconciling them with Bootstrap.

        **Parameters:**<br>
        `num_samples`: int, number of samples generated from coherent distribution.<br>

        **Returns:**<br>
        `samples`: Coherent samples of size (`base`, `horizon`, `num_samples`).
        """
        residuals = self.y_insample - self.y_hat_insample
        h = self.y_hat.shape[1]

        #removing nas from residuals
        residuals = residuals[:, np.isnan(residuals).sum(axis=0) == 0]
        sample_idx = np.arange(residuals.shape[1] - h)
        state = np.random.RandomState(self.seed)
        samples_idx = state.choice(sample_idx, size=num_samples)
        samples = [self.y_hat + residuals[:, idx:(idx + h)] for idx in samples_idx]
        SP = self.S @ self.P
        samples = np.apply_along_axis(lambda path: np.matmul(SP, path),
                                      axis=1, arr=samples)
        samples = np.stack(samples)

        # [samples, N, H] -> [N, H, samples]
        samples = samples.transpose((1, 2, 0))
        return samples

    def get_prediction_levels(self, res, level):
        """ Adds reconciled forecast levels to results dictionary """
        samples = self.get_samples(num_samples=self.num_samples)
        for lv in level:
            min_q = (100 - lv) / 200
            max_q = min_q + lv / 100
            res[f'lo-{lv}'] = np.quantile(samples, min_q, axis=2)
            res[f'hi-{lv}'] = np.quantile(samples, max_q, axis=2)
        return res

    def get_prediction_quantiles(self, res, quantiles):
        """ Adds reconciled forecast quantiles to results dictionary """
        samples = self.get_samples(num_samples=self.num_samples)

        # [Q, N, H] -> [N, H, Q]
        sample_quantiles = np.quantile(samples, quantiles, axis=2)
        res['quantiles'] = sample_quantiles.transpose((1, 2, 0))
        return res

# %% ../nbs/probabilistic_methods.ipynb 14
class PERMBU:
    """ PERMBU Probabilistic Reconciliation Class.

    The PERMBU method leverages empirical bottom-level marginal distributions 
    with empirical copula functions (describing bottom-level dependencies) to 
    generate the distribution of aggregate-level distributions using BottomUp 
    reconciliation. The sample reordering technique in the PERMBU method reinjects 
    multivariate dependencies into independent bottom-level samples.

        Algorithm:
        1.   For all series compute conditional marginals distributions.
        2.   Compute residuals $\hat{\epsilon}_{i,t}$ and obtain rank permutations.
        2.   Obtain K-sample from the bottom-level series predictions.
        3.   Apply recursively through the hierarchical structure:<br>
            3.1.   For a given aggregate series $i$ and its children series:<br>
            3.2.   Obtain children's empirical joint using sample reordering copula.<br>
            3.2.   From the children's joint obtain the aggregate series's samples.    

    **Parameters:**<br>
    `S`: np.array, summing matrix of size (`base`, `bottom`).<br>
    `tags`: Each key is a level and each value its `S` indices.<br>
    `y_insample`: Insample values of size (`base`, `insample_size`).<br>
    `y_hat_insample`: Insample point forecasts of size (`base`, `insample_size`).<br>
    `sigmah`: np.array, forecast standard dev. of size (`base`, `horizon`).<br>
    `num_samples`: int, number of normal prediction samples generated.<br>
    `seed`: int, random seed for numpy generator's replicability.<br>

    **References:**<br>
    - [Taieb, Souhaib Ben and Taylor, James W and Hyndman, Rob J. (2017). 
    Coherent probabilistic forecasts for hierarchical time series. 
    International conference on machine learning ICML.](https://proceedings.mlr.press/v70/taieb17a.html)
    """
    def __init__(self,
                 S: np.ndarray,
                 tags: Dict[str, np.ndarray],
                 y_hat: np.ndarray,
                 y_insample: np.ndarray,
                 y_hat_insample: np.ndarray,
                 sigmah: np.ndarray,
                 num_samples: int=None,
                 seed: int=0,
                 P: np.ndarray = None):
        # PERMBU only works for strictly hierarchical structures
        if not is_strictly_hierarchical(S, tags):
            raise ValueError('PERMBU probabilistic reconciliation requires strictly hierarchical structures.')
        self.S = S
        self.P = P
        self.y_hat = y_hat
        self.y_insample = y_insample
        self.y_hat_insample = y_hat_insample
        self.sigmah = sigmah
        self.num_samples = num_samples
        self.seed = seed

    def _obtain_ranks(self, array):
        """ Vector ranks

        Efficiently obtain vector ranks.
        Example `array=[4,2,7,1]` -> `ranks=[2, 1, 3, 0]`.

        **Parameters**<br>
        `array`: np.array, matrix with floats or integers on which the 
                ranks will be computed on the second dimension.<br>

        **Returns**<br>
        `ranks`: np.array, matrix with ranks along the second dimension.<br>
        """
        temp = array.argsort(axis=1)
        ranks = np.empty_like(temp)
        a_range = np.arange(temp.shape[1])
        for i_row in range(temp.shape[0]):
            ranks[i_row, temp[i_row,:]] = a_range
        return ranks

    def _permutate_samples(self, samples, permutations):
        """ Permutate Samples

        Applies efficient vectorized permutation on the samples.

        **Parameters**<br>
        `samples`: np.array [series,samples], independent base samples.<br>
        `permutations`: np.array [series,samples], permutation ranks with wich
                  which `samples` dependence will be restored see `_obtain_ranks`.<br>

        **Returns**<br>
        `permutated_samples`: np.array.<br>
        """
        # Generate auxiliary and flat permutation indexes
        n_rows, n_cols = permutations.shape
        aux_row_idx = np.arange(n_rows)[:,None] * n_cols
        aux_row_idx = np.repeat(aux_row_idx, repeats=n_cols, axis=1)
        permutate_idxs = permutations.flatten() + aux_row_idx.flatten()

        # Apply flat permutation indexes and recover original shape
        permutated_samples = samples.flatten()
        permutated_samples = permutated_samples[permutate_idxs]
        permutated_samples = permutated_samples.reshape(n_rows, n_cols)
        return permutated_samples
    
    def _permutate_predictions(self, prediction_samples, permutations):
        """ Permutate Prediction Samples

        Applies permutations to prediction_samples across the horizon.

        **Parameters**<br>
        `prediction_samples`: np.array [series,horizon,samples], independent 
                  base prediction samples.<br>
        `permutations`: np.array [series, samples], permutation ranks with which
                  `samples` dependence will be restored see `_obtain_ranks`.
                  it can also apply a random permutation.<br>

        **Returns**<br>
        `permutated_prediction_samples`: np.array.<br>
        """
        # Apply permutation throughout forecast horizon
        permutated_prediction_samples = prediction_samples.copy()

        _, n_horizon, _ = prediction_samples.shape
        for t in range(n_horizon):
            permutated_prediction_samples[:,t,:] = \
                              self._permutate_samples(prediction_samples[:,t,:],
                                                      permutations)
        return permutated_prediction_samples

    def _nonzero_indexes_by_row(self, M):
        return [np.nonzero(M[row,:])[0] for row in range(len(M))]

    def get_samples(self, num_samples: int=None):
        """PERMBU Sample Reconciliation Method.

        Applies PERMBU reconciliation method as defined by Taieb et. al 2017.
        Generating independent base prediction samples, restoring its multivariate
        dependence using estimated copula with reordering and applying the BottomUp
        aggregation to the new samples.

        **Parameters:**<br>
        `num_samples`: int, number of samples generated from coherent distribution.<br>

        **Returns:**<br>
        `samples`: Coherent samples of size (`base`, `horizon`, `num_samples`).
        """
        # Compute residuals and rank permutations
        residuals = self.y_insample - self.y_hat_insample
        residuals = residuals[:, np.isnan(residuals).sum(axis=0) == 0]

        # Expand residuals to match num_samples [(a,b),T] -> [(a,b),num_samples]
        if num_samples > residuals.shape[1]:
            residuals_expansion = np.random.choice(residuals.shape[1], size=num_samples)
            residuals = residuals[:,residuals_expansion]
        rank_permutations = self._obtain_ranks(residuals)

        # Sample h step-ahead base marginal distributions
        if num_samples is None:
            num_samples = residuals.shape[1]

        state = np.random.RandomState(self.seed)
        n_series, n_horizon = self.y_hat.shape

        base_samples = np.array([
            state.normal(loc=m, scale=s, size=num_samples) for m, s in \
            zip(self.y_hat.flatten(), self.sigmah.flatten())
        ])
        base_samples = base_samples.reshape(n_series, n_horizon, num_samples)

        # Initialize PERMBU utility
        rec_samples = base_samples.copy()
        encoder = OneHotEncoder(sparse=False, dtype=np.float32)
        hier_links = np.vstack(self._nonzero_indexes_by_row(self.S.T))

        # BottomUp hierarchy traversing
        hier_levels = hier_links.shape[1]-1
        for level_idx in reversed(range(hier_levels)):
            # Obtain aggregation matrix from parent/children links
            children_links = np.unique(hier_links[:,level_idx:level_idx+2], 
                                       axis=0)
            children_idxs = np.unique(children_links[:,1])
            parent_idxs = np.unique(children_links[:,0])
            Agg = encoder.fit_transform(children_links).T
            Agg = Agg[:len(parent_idxs),:]

            # Permute childrenum_samples for each prediction step
            children_permutations = rank_permutations[children_idxs, :]
            childrenum_samples = rec_samples[children_idxs,:,:]
            childrenum_samples = self._permutate_predictions(
                prediction_samples=childrenum_samples,
                permutations=children_permutations
            )

            # Overwrite hier_samples with BottomUp aggregation
            # and randomly shuffle parent predictions after aggregation
            parent_samples = np.einsum('ab,bhs->ahs', Agg, childrenum_samples)
            random_permutation = np.array([
                np.random.permutation(np.arange(num_samples)) \
                for serie in range(len(parent_samples))
            ])
            parent_samples = self._permutate_predictions(
                prediction_samples=parent_samples,
                permutations=random_permutation
            )

            rec_samples[parent_idxs,:,:] = parent_samples
        return rec_samples

    def get_prediction_levels(self, res, level):
        """ Adds reconciled forecast levels to results dictionary """
        samples = self.get_samples(num_samples=self.num_samples)
        for lv in level:
            min_q = (100 - lv) / 200
            max_q = min_q + lv / 100
            res[f'lo-{lv}'] = np.quantile(samples, min_q, axis=2)
            res[f'hi-{lv}'] = np.quantile(samples, max_q, axis=2)
        return res

    def get_prediction_quantiles(self, res, quantiles):
        """ Adds reconciled forecast quantiles to results dictionary """
        samples = self.get_samples(num_samples=self.num_samples)

        # [Q, N, H] -> [N, H, Q]
        sample_quantiles = np.quantile(samples, quantiles, axis=2)
        res['quantiles'] = sample_quantiles.transpose((1, 2, 0))
        return res
