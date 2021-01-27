import pytest
import numpy as np

from ngmix import DiagonalJacobian, GMix
from ngmix.em import GMixEM, prep_image
from ngmix import Observation
from ngmix.priors import srandu


def get_obs(*, rng, ngauss, pixel_scale, noise=0.0):

    counts = 100.0
    dims = [25, 25]
    cen = (np.array(dims) - 1.0) / 2.0
    jacob = DiagonalJacobian(scale=pixel_scale, row=cen[0], col=cen[1])

    T_1 = 0.55  # arcsec**2

    e1_1 = 0.1
    e2_1 = 0.05

    irr_1 = T_1 / 2.0 * (1 - e1_1)
    irc_1 = T_1 / 2.0 * e2_1
    icc_1 = T_1 / 2.0 * (1 + e1_1)

    cen1 = [-3.25*pixel_scale, -3.25*pixel_scale]

    if ngauss == 2:

        frac1 = 0.4
        frac2 = 0.6

        cen2 = [3.0*pixel_scale, 0.5*pixel_scale]

        T_2 = T_1/2

        e1_1 = 0.1
        e2_1 = 0.05
        e1_2 = -0.2
        e2_2 = -0.1

        counts_1 = frac1 * counts
        counts_2 = frac2 * counts

        irr_1 = T_1 / 2.0 * (1 - e1_1)
        irc_1 = T_1 / 2.0 * e2_1
        icc_1 = T_1 / 2.0 * (1 + e1_1)

        irr_2 = T_2 / 2.0 * (1 - e1_2)
        irc_2 = T_2 / 2.0 * e2_2
        icc_2 = T_2 / 2.0 * (1 + e1_2)

        pars = [
            counts_1,
            cen1[0],
            cen1[1],
            irr_1,
            irc_1,
            icc_1,
            counts_2,
            cen2[0],
            cen2[1],
            irr_2,
            irc_2,
            icc_2,
        ]

    elif ngauss == 1:

        pars = [
            counts,
            cen1[0],
            cen1[1],
            irr_1,
            irc_1,
            icc_1,
        ]

    gm = GMix(pars=pars)
    im0 = gm.make_image(dims, jacobian=jacob)
    im = im0 + noise * np.random.randn(im0.size).reshape(dims)
    obs = Observation(im, jacobian=jacob)

    return obs, gm


@pytest.mark.parametrize('noise', [0.0, 0.05])
def test_1gauss(noise):
    """
    see if we can recover the input with no noise to
    high precision even with a bad guess

    Use ngmix to make the image to make sure there are
    no pixelization effects
    """

    pixel_scale = 0.263
    rng = np.random.RandomState(42587)
    ngauss = 1
    obs, gm = get_obs(rng=rng, ngauss=ngauss, pixel_scale=0.263, noise=noise)

    imsky, sky = prep_image(obs.image)
    obs_sky = Observation(imsky, jacobian=obs.jacobian)

    pars = gm.get_full_pars()
    counts = pars[0]

    gm_guess = gm.copy()
    gm_guess._data["p"] += counts/10 * srandu(rng=rng)
    gm_guess._data["row"] += 4 * pixel_scale * srandu(rng=rng)
    gm_guess._data["col"] += 4 * pixel_scale * srandu(rng=rng)
    gm_guess._data["irr"] += 0.5 * pixel_scale**2 * srandu(rng=rng)
    gm_guess._data["irc"] += 0.5 * pixel_scale**2 * srandu(rng=rng)
    gm_guess._data["icc"] += 0.5 * pixel_scale**2 * srandu(rng=rng)

    em = GMixEM(obs_sky)
    em.go(gm_guess, sky)

    fit_gm = em.get_gmix()
    res = em.get_result()
    assert res['flags'] == 0

    fitpars = fit_gm.get_full_pars()

    if noise == 0.0:
        tol = 1.0e-4
        assert (fitpars[0]/pars[0]-1) < tol
        assert (fitpars[3]/pars[3]-1) < tol
        assert (fitpars[4]/pars[4]-1) < tol
        assert (fitpars[5]/pars[5]-1) < tol

    # check reconstructed image allowing for noise
    imfit = em.make_image()
    imtol = 0.001 / pixel_scale**2 + noise*5
    assert np.all((imfit - obs.image) < imtol)


@pytest.mark.parametrize('noise', [0.0, 0.05])
def test_2gauss(noise):
    """
    see if we can recover the input with no noise to
    high precision even with a bad guess

    Use ngmix to make the image to make sure there are
    no pixelization effects
    """

    pixel_scale = 0.263
    rng = np.random.RandomState(42587)
    ngauss = 2
    obs, gm = get_obs(rng=rng, ngauss=ngauss, pixel_scale=0.263, noise=noise)

    imsky, sky = prep_image(obs.image)
    obs_sky = Observation(imsky, jacobian=obs.jacobian)

    pars = gm.get_full_pars()
    counts_1 = pars[0]

    gm_guess = gm.copy()
    gm_guess._data["p"] += counts_1/10 * srandu(2, rng=rng)
    gm_guess._data["row"] += 4 * pixel_scale * srandu(2, rng=rng)
    gm_guess._data["col"] += 4 * pixel_scale * srandu(2, rng=rng)
    gm_guess._data["irr"] += 0.5 * pixel_scale**2 * srandu(2, rng=rng)
    gm_guess._data["irc"] += 0.5 * pixel_scale**2 * srandu(2, rng=rng)
    gm_guess._data["icc"] += 0.5 * pixel_scale**2 * srandu(2, rng=rng)

    em = GMixEM(obs_sky)
    em.go(gm_guess, sky)

    fit_gm = em.get_gmix()
    res = em.get_result()
    assert res['flags'] == 0

    fitpars = fit_gm.get_full_pars()

    f1 = pars[0]
    f2 = pars[6]
    if f1 > f2:
        indices = [1, 0]
    else:
        indices = [0, 1]

    # only check pars for no noise
    if noise == 0.0:
        for i in range(ngauss):
            start = i*6
            end = (i+1)*6

            truepars = pars[start:end]

            fitstart = indices[i]*6
            fitend = (indices[i]+1)*6
            thispars = fitpars[fitstart:fitend]

            tol = 1.0e-4
            assert (thispars[0]/truepars[0]-1) < tol
            assert (thispars[3]/truepars[3]-1) < tol
            assert (thispars[4]/truepars[4]-1) < tol
            assert (thispars[5]/truepars[5]-1) < tol

    # check reconstructed image allowing for noise
    imfit = em.make_image()
    imtol = 0.001 / pixel_scale**2 + noise*5
    assert np.all((imfit - obs.image) < imtol)
