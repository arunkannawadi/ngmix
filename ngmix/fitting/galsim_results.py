__all__ = [
    'GalsimFitModel', 'GalsimSpergelFitModel',
    'GalsimMoffatFitModel', 'GalsimPSFFitModel',
]
import numpy as np
from .results import FitModel, PSFFluxFitModel
from ..gexceptions import GMixRangeError
from ..defaults import copy_if_needed, LOWVAL
from .. import observation
from ..observation import Observation, ObsList, MultiBandObsList


class GalsimFitModel(FitModel):
    """
    Represent a fitting model for fitting 6 parameter models with galsim, as well
    as generate images and mixtures for the best fit model

    Parameters
    ----------
    obs: observation(s)
        Observation, ObsList, or MultiBandObsList
    model: string
        e.g. 'exp', 'spergel'
    guess: array-like
        starting parameters for the lm fitter
    prior: ngmix prior, optional
        For example ngmix.priors.PriorSimpleSep can
        be used as a separable prior on center, g, size, flux.
    """

    def __init__(self, obs, model, guess, prior=None):
        self.model = model
        self['model'] = model
        self._set_model_class()
        self._set_prior(prior=prior)
        self._set_bounds()

        self._set_kobs(obs)
        self._set_n_prior_pars()
        self._set_totpix()
        self._set_fdiff_size()
        self._init_model_images()
        self._set_band_pars()

        guess = self._get_guess(guess)

    def calc_fdiff(self, pars):
        """

        vector with (model-data)/error.

        The npars elements contain -ln(prior)
        """

        # we cannot keep sending existing array into leastsq, don't know why
        fdiff = np.zeros(self.fdiff_size)

        try:

            self._fill_models(pars)

            start = self._fill_priors(pars, fdiff)

            for band in range(self.nband):

                kobs_list = self.mb_kobs[band]
                for kobs in kobs_list:

                    meta = kobs.meta
                    kmodel = meta["kmodel"]
                    ierr = meta["ierr"]

                    scratch = meta["scratch"]

                    # model-data
                    scratch.array[:, :] = kmodel.array[:, :]
                    scratch -= kobs.kimage

                    # (model-data)/err
                    scratch.array.real[:, :] *= ierr.array[:, :]
                    scratch.array.imag[:, :] *= ierr.array[:, :]

                    # now copy into the full fdiff array
                    imsize = scratch.array.size

                    fdiff[start:start + imsize] = scratch.array.real.ravel()

                    start += imsize

                    fdiff[start:start + imsize] = scratch.array.imag.ravel()

                    start += imsize

        except GMixRangeError:
            fdiff[:] = LOWVAL

        return fdiff

    def _fill_models(self, pars):
        """
        input pars are in linear space

        Fill the list of lists of gmix objects for the given parameters
        """
        try:
            for band, kobs_list in enumerate(self.mb_kobs):
                # pars for this band, in linear space
                band_pars = self.get_band_pars(pars, band)

                for i, kobs in enumerate(kobs_list):

                    gal = self.make_model(band_pars)

                    meta = kobs.meta

                    kmodel = meta["kmodel"]

                    gal._drawKImage(kmodel)

                    if kobs.has_psf():
                        kmodel *= kobs.psf.kimage
        except RuntimeError as err:
            raise GMixRangeError(str(err))

    def make_model(self, pars):
        """
        make the galsim model
        """

        model = self.make_round_model(pars)

        shift = pars[0:0+2]
        g1 = pars[2]
        g2 = pars[3]

        # argh another generic error
        try:
            model = model.shear(g1=g1, g2=g2)
        except ValueError as err:
            raise GMixRangeError(str(err))

        model = model.shift(shift)
        return model

    def make_round_model(self, pars):
        """
        make the round galsim model, unshifted
        """

        r50 = pars[4]
        flux = pars[5]

        if r50 < 0.0001:
            raise GMixRangeError("low r50: %g" % r50)

        # this throws a generic runtime error so there is no way to tell what
        # went wrong

        try:
            model = self._model_class(half_light_radius=r50, flux=flux,)
        except RuntimeError as err:
            raise GMixRangeError(str(err))

        return model

    def _set_model_class(self):
        import galsim

        if self.model == "exp":
            self._model_class = galsim.Exponential
        elif self.model == "dev":
            self._model_class = galsim.DeVaucouleurs
        elif self.model == "gauss":
            self._model_class = galsim.Gaussian
        else:
            raise NotImplementedError("can't fit '%s'" % self.model)

    def get_band_pars(self, pars_in, band):
        """
        Get pars for the specified band

        input pars are [c1, c2, e1, e2, r50, flux1, flux2, ....]
        """

        pars = self._band_pars

        pars[0:5] = pars_in[0:5]
        pars[5] = pars_in[5 + band]
        return pars

    def _set_totpix(self):
        """
        Make sure the data are consistent.
        """

        totpix = 0
        for kobs_list in self.mb_kobs:
            for kobs in kobs_list:
                totpix += kobs.kimage.array.size

        self.totpix = totpix

    def _convert2kobs(self, obs):
        kobs = observation.make_kobs(obs)

        return kobs

    def _set_kobs(self, obs_in, **keys):
        """
        Input should be an Observation, ObsList, or MultiBandObsList
        """

        if isinstance(obs_in, (Observation, ObsList, MultiBandObsList)):
            kobs = self._convert2kobs(obs_in)
        else:
            kobs = observation.get_kmb_obs(obs_in)

        self.mb_kobs = kobs
        self.nband = len(kobs)

    def _set_prior(self, prior=None):
        self.prior = prior

    def _set_n_prior_pars(self):
        if self.prior is None:
            self.n_prior_pars = 0
        else:
            #                 c1  c2  e1e2  r50  fluxes
            self.n_prior_pars = 1 + 1 + 1 + 1 + self.nband

    def _set_fdiff_size(self):
        # we have 2*totpix, since we use both real and imaginary
        # parts
        self.fdiff_size = self.n_prior_pars + 2 * self.totpix

    def _create_models_in_kobs(self, kobs):
        ex = kobs.kimage

        meta = kobs.meta
        meta["kmodel"] = ex.copy()
        meta["scratch"] = ex.copy()

    def _init_model_images(self):
        """
        add model image entries to the metadata for
        each observation

        these will get filled in
        """

        for kobs_list in self.mb_kobs:
            for kobs in kobs_list:
                meta = kobs.meta

                weight = kobs.weight
                ierr = weight.copy()
                ierr.setZero()

                w = np.where(weight.array > 0)
                if w[0].size > 0:
                    ierr.array[w] = np.sqrt(weight.array[w])

                meta["ierr"] = ierr
                self._create_models_in_kobs(kobs)

    def _check_guess(self, guess):
        """
        check the guess by making a model and checking for an
        exception
        """

        guess = np.array(guess, dtype="f8", copy=copy_if_needed)
        if guess.size != self.npars:
            raise ValueError(
                "expected %d entries in the "
                "guess, but got %d" % (self.npars, guess.size)
            )

        for band in range(self.nband):
            band_pars = self.get_band_pars(guess, band)
            # just doing this to see if an exception is raised. This
            # will bother flake8
            gal = self.make_model(band_pars)  # noqa

        return guess

    def _get_guess(self, guess):
        """
        make sure the guess has the right size and meets the model
        restrictions
        """

        guess = self._check_guess(guess)
        return guess

    def _set_npars(self):
        """
        nband should be set in set_lists, called before this
        """
        self.npars = get_galsim_npars(self.model, self.nband)

    def _set_band_pars(self):
        """
        this is the array we fill with pars for a specific band
        """
        self._set_npars()

        npars_band = self.npars - self.nband + 1
        self._band_pars = np.zeros(npars_band)

    def set_fit_result(self, result):
        """
        Get some fit statistics for the input pars.
        """

        self.update(result)
        if self['flags'] == 0:
            self["s2n_r"] = self.calc_s2n_r(self['pars'])
            self._set_g()
            self._set_flux()

    def calc_s2n_r(self, pars):
        """
        we already have the round r50, so just create the
        models and don't shear them
        """

        s2n_sum = 0.0
        for band, kobs_list in enumerate(self.mb_kobs):
            # pars for this band, in linear space
            band_pars = self.get_band_pars(pars, band)

            for i, kobs in enumerate(kobs_list):
                meta = kobs.meta
                weight = kobs.weight

                round_pars = band_pars.copy()
                round_pars[2:2+2] = 0.0
                gal = self.make_model(round_pars)

                kmodel = meta["kmodel"]

                gal.drawKImage(image=kmodel)

                if kobs.has_psf():
                    kmodel *= kobs.psf.kimage
                kmodel.real.array[:, :] *= kmodel.real.array[:, :]
                kmodel.imag.array[:, :] *= kmodel.imag.array[:, :]

                kmodel.real.array[:, :] *= weight.array[:, :]
                kmodel.imag.array[:, :] *= weight.array[:, :]

                s2n_sum += kmodel.real.array.sum()
                s2n_sum += kmodel.imag.array.sum()

        if s2n_sum > 0.0:
            s2n = np.sqrt(s2n_sum)
        else:
            s2n = 0.0

        return s2n


class GalsimSpergelFitModel(GalsimFitModel):
    """
    Represent a fitting model for fitting the spergel model with galsim, as
    well as generate images and mixtures for the best fit model

    parameters
    ----------
    obs: observation(s)
        Observation, ObsList, or MultiBandObsList
    guess: array-like
        starting parameters for the lm fitter
    prior: ngmix prior, optional
        For example ngmix.priors.PriorSimpleSep can
        be used as a separable prior on center, g, size, flux.
    """

    def __init__(self, obs, guess, prior=None):
        super().__init__(obs=obs, model='spergel', guess=guess, prior=prior)

    def _set_model_class(self):
        import galsim

        self._model_class = galsim.Spergel

    def make_round_model(self, pars):
        """
        make the galsim Spergel model
        """
        import galsim

        r50 = pars[4]
        nu = pars[5]
        flux = pars[6]

        # generic RuntimeError thrown
        try:
            gal = galsim.Spergel(nu, half_light_radius=r50, flux=flux,)
        except RuntimeError as err:
            raise GMixRangeError(str(err))

        return gal

    def get_band_pars(self, pars_in, band):
        """
        Get linear pars for the specified band

        input pars are [c1, c2, e1, e2, r50, nu, flux1, flux2, ....]
        """

        pars = self._band_pars

        pars[0:6] = pars_in[0:6]
        pars[6] = pars_in[6 + band]
        return pars

    def _set_n_prior_pars(self):
        if self.prior is None:
            self.n_prior_pars = 0
        else:
            #                 c1  c2  e1e2  r50  nu   fluxes
            self.n_prior_pars = 1 + 1 + 1 + 1 + 1 + self.nband


class GalsimMoffatFitModel(GalsimFitModel):
    """
    Represent a fitting model for fitting the moffat profile with galsim, as
    well as generate images and mixtures for the best fit model

    Parameters
    ----------
    obs: observation(s)
        Observation, ObsList, or MultiBandObsList
    guess: array-like
        starting parameters for the lm fitter
    prior: ngmix prior, optional
        For example ngmix.priors.PriorSimpleSep can
        be used as a separable prior on center, g, size, flux.
    """

    def __init__(self, obs, guess, prior=None):
        super().__init__(obs=obs, model='moffat', guess=guess, prior=prior)

    def _set_model_class(self):
        import galsim

        self._model_class = galsim.Moffat

    def make_round_model(self, pars):
        """
        make the galsim Moffat model
        """
        import galsim

        r50 = pars[4]
        beta = pars[5]
        flux = pars[6]

        # generic RuntimeError thrown
        try:
            gal = galsim.Moffat(beta, half_light_radius=r50, flux=flux,)
        except RuntimeError as err:
            raise GMixRangeError(str(err))

        return gal

    def get_band_pars(self, pars_in, band):
        """
        Get linear pars for the specified band

        input pars are [c1, c2, e1, e2, r50, beta, flux1, flux2, ....]
        """

        pars = self._band_pars

        pars[0:6] = pars_in[0:6]
        pars[6] = pars_in[6 + band]
        return pars

    def _set_prior(self, prior=None):
        self.prior = prior

    def _set_n_prior_pars(self):
        if self.prior is None:
            self.n_prior_pars = 0
        else:
            #                 c1  c2  e1e2  r50  beta   fluxes
            self.n_prior_pars = 1 + 1 + 1 + 1 + 1 + self.nband


class GalsimPSFFitModel(PSFFluxFitModel):
    """
    Represent a fitting model template flux fits

    Parameters
    ----------
    obs: observation(s)
        Observation, ObsList, or MultiBandObsList
    model: galsim model, optional
        A Galsim model, e.g. Exponential.  If not sent,
        a psf flux is measured
    draw_method: str
        Galsim drawing method, default 'auto'
    interp: string
        type of interpolation when using the PSF image
        rather than psf models.  Default lanzcos15
    """
    def __init__(
        self,
        obs,
        model=None,
        draw_method='auto',
        interp=observation.DEFAULT_XINTERP,
    ):

        self.galsim_model = model

        if self.galsim_model is not None:
            self.galsim_model = self.galsim_model.withFlux(1.0)

        self.interp = interp
        self.draw_method = draw_method

        self['model'] = 'template'
        self.npars = 1

        self._set_obs(obs)

    def _get_model(self, iobs, flux=None):
        """
        get the model image
        """

        if flux is not None:
            model = self.template_list[iobs].copy()
            model *= flux / model.sum()
        else:
            model = self.template_list[iobs]

        return model

    def _do_draw(self, obj, ncol, nrow, jac):
        wcs = jac.get_galsim_wcs()

        # note reverse for galsim
        canonical_center = (np.array((ncol, nrow)) - 1.0) / 2.0
        jrow, jcol = jac.get_cen()
        offset = (jcol, jrow) - canonical_center
        try:
            gim = obj.drawImage(
                nx=ncol,
                ny=nrow,
                wcs=wcs,
                offset=offset,
                method=self.draw_method,
            )
        except RuntimeError as err:
            # argh another generic exception
            raise GMixRangeError(str(err))

        return gim

    def _set_obs(self, obs_in):
        """
        Input should be an Observation, ObsList
        """

        if isinstance(obs_in, Observation):
            obs_list = ObsList()
            obs_list.append(obs_in)

        elif isinstance(obs_in, ObsList):
            obs_list = obs_in

        else:
            raise ValueError("obs should be Observation or ObsList")

        self.obs = obs_list
        self._set_totpix()
        self._set_psf_models()
        self._set_template_images()

    def _set_psf_models(self):
        """
        we use the psfs stored in the observations as
        the psf model
        """
        import galsim

        models = []
        for obs in self.obs:

            psf_jac = obs.psf.jacobian
            psf_im = obs.psf.image.copy()

            psf_im *= 1.0 / psf_im.sum()

            nrow, ncol = psf_im.shape
            canonical_center = (np.array((ncol, nrow)) - 1.0) / 2.0
            jrow, jcol = psf_jac.get_cen()
            offset = (jcol, jrow) - canonical_center

            psf_gsimage = galsim.Image(
                psf_im, wcs=obs.psf.jacobian.get_galsim_wcs(),
            )
            psf_ii = galsim.InterpolatedImage(
                psf_gsimage, offset=offset, x_interpolant=self.interp,
            )

            models.append(psf_ii)

        self.psf_models = models

    def _set_template_images(self):
        """
        set the images used for the templates
        """
        import galsim

        image_list = []

        for i, obs in enumerate(self.obs):

            psf_model = self.psf_models[i]

            if self.galsim_model is not None:
                obj = galsim.Convolve(self.galsim_model, psf_model)
            else:
                obj = psf_model

            nrow, ncol = obs.image.shape

            gim = self._do_draw(obj, ncol, nrow, obs.jacobian,)

            image_list.append(gim.array)

        self.template_list = image_list


def get_galsim_npars(model, nband):
    """
    get number of parameters for a galsim model

    Parameters
    ----------
    model: str
        Model string, e.g. exp, dev
    nband: int
        Number of bands

    Returns
    -------
    number of parameters
    """
    if model in ['exp', 'dev', 'gauss']:
        return 5 + nband
    elif model in ['spergel', 'moffat']:
        return 6 + nband
    else:
        raise ValueError('bad model %s' % model)
