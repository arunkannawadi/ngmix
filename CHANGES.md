## v1.3.9

### bug fixes

- metacal was reconvolving by the pixel *twice*, which resulted in larger
  reconvolved PSFs and thus somewhat lower, but still accurate, response than
  the pixel was included once. This did not cause any bias. 

## v1.3.8

### bug fixes

- fix bug not updating pixel array when adding noise in metacal

### new features

- added writeable context for observations, now returned references
  for observation images etc. are read only unless in the writeable
  context
- jacobian getter returns new Jacobian with readonly view, rather
  than a copy
- added more unit tests

## v1.3.7

### new features

- Add option to not store pixels

## v1.3.6

### bug fixes

- fixed bug in T fraction sum for `dev` profiles
- fixed bugs for the full bulge+disk fitter

### new features

- added order 5 fast exponential to fastexp.py which
  is exported as fexp. This has satisfactory accuracy
  but is much faster than expd in some real world
  scenarios.  Modified the tests accordinly.
- added a Gaussian moments fitter
- added 5 gaussian coellip fitting in the coellip
  psf fitter

## v1.3.5

### bug fixes

- better fast exponential function approximation
- bug in gaussian aperture flux calculation for cm

### new features

- unit tests and travis CI for core APIs


## v1.3.4

### new features

- analytic Gaussian aperture fluxes


## v1.3.3

### bug fixes

- fixed bug in BDF Gaussian aperture fluxes


## v1.3.2

### bug fixes

- Use psf_cutout_row and col for center in psf obs for
  meds reader
