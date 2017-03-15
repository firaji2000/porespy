import scipy as sp
import scipy.ndimage as spim
from skimage.morphology import ball, disk, square, cube
import OpenPNM as op

def randomize_colors(im, keep_vals=[0]):
    r'''
    Takes a greyscale image and randomly shuffles the greyscale values, so that
    all voxels labeled X will be labelled Y, and all voxels labeled Y will be
    labeled Z, where X, Y, Z and so on are randomly selected from the values
    in the input image.

    This function is useful for improving the visibility of images with
    neighboring regions that are only incrementally different from each other,
    such as that returned by `scipy.ndimage.label`.

    Parameters
    ----------
    im : array_like
        An ND image of greyscale values.

    keep_vals : array_like
        Indicate which voxel values should NOT be altered.  The default is
        `[0]` which is useful for leaving the background of the image
        untouched.

    Returns
    -------
    An image the same size and type as `im` but with the greyscale values
    reassigned.  The unique values in both the input and output images will
    be identical.

    Notes
    -----
    If the greyscale values in the input image are not contiguous then the
    neither will they be in the output.

    Examples
    --------
    >>> import porespy as ps
    >>> import scipy as sp
    >>> sp.random.seed(0)
    >>> im = sp.random.randint(low=0, high=5, size=[4, 4])
    >>> print(im)
    [[4 0 3 3]
     [3 1 3 2]
     [4 0 0 4]
     [2 1 0 1]]
    >>> im_rand = ps.tools.randomize_colors(im)
    >>> print(im_rand)
    [[2 0 4 4]
     [4 1 4 3]
     [2 0 0 2]
     [3 1 0 1]]

    As can be seen, the 2's have become 3, 3's have become 4, and 4's have
    become 2.  1's remained 1 by random accident.  0's remain zeros by default,
    but this can be controlled using the `keep_vals` argument.

    '''
    im_flat = im.flatten()
    keep_vals = sp.array(keep_vals)
    swap_vals = ~sp.in1d(im_flat, keep_vals)
    im_vals = sp.unique(im_flat[swap_vals])
    new_vals = sp.random.permutation(im_vals)
    im_map = sp.zeros(shape=[sp.amax(im_vals) + 1, ], dtype=int)
    im_map[im_vals] = new_vals
    im_new = im_map[im_flat]
    im_new = sp.reshape(im_new, newshape=sp.shape(im))
    return im_new


def flood(im, mode='max', func=None):
    r"""
    Floods/fills each region in an image with a single value based on the
    specific values in the region.  The ```mode``` argument is used to
    determine how the value is calculated.

    Parameters
    ----------
    im : array_like
        An ND image with isolated regions containing 0's elsewhere.

    mode : string
        Specifies how to determine which value should be used to flood each
        region.  Options are:

    *'max'* : Floods each region with the local maximum in that region

    *'min'* : Floods each region the local minimum in that region

    *'mean'* : Floods each region with the mean value in that region

    *'size'* : Floods each region with the size of that region

    func : function handle
        Can be used to pass in a special function that is used to evaluate
        some property for each region.  For instance, passing  ```scipy.amax```
        is equivalent to specifying ```mode``` of 'max'.

    Returns
    -------
    An ND-array the same size as ```im``` with new values placed in each
    forground voxel based on the ```mode``` (or ```func```)

    """
    labels, N = spim.label(im)
    flooded_im = sp.zeros_like(im, dtype=float)
    if func is None:
        if mode.startswith('max'):
            func = sp.amax
        elif mode.startswith('min'):
            func = sp.amin
        elif mode.startswith('mean'):
            func = sp.mean
        elif mode.startswith('size'):
            func = sp.size
    for L in range(1, N):
        inds = sp.where(labels == L)
        val = func(im[inds])
        flooded_im[inds] = val
    return flooded_im


def concentration_transform(im):
    import pyamg
    net = op.Network.Cubic(shape=im.shape)
    net.fromarray(im, propname='pore.void')
    net.fromarray(~im, propname='pore.solid')
    geom = op.Geometry.GenericGeometry(network=net, pores=net.Ps, throats=net.Ts)
    phase = op.Phases.GenericPhase(network=net)
    phys = op.Physics.GenericPhysics(network=net, phase=phase, geometry=geom)
    phys['throat.diffusive_conductance'] = 1
    phys['pore.A1'] = 1
    phys['pore.A2'] = 2
    phys.models.add(propname='pore.sink',
                    model=op.Physics.models.generic_source_term.linear,
                    A1='pore.A1', A2='pore.A2')
    alg = op.Algorithms.FickianDiffusion(network=net, phase=phase)
    alg.set_boundary_conditions(bctype='Neumann', bcvalue=-1, pores=net.pores('void'))
    alg.set_boundary_conditions(bctype='Dirichlet', bcvalue=0, pores=net.pores('solid'))
#    alg.set_source_term(source_name='pore.sink', pores=net.pores('solid'))
    alg.setup()
    ml = pyamg.ruge_stuben_solver(alg.A)
    X = ml.solve(alg.b)
    ct = net.asarray(X).squeeze()
    return ct


def make_contiguous(im):
    r"""
    Take an image with arbitrary greyscale values and adjust them to ensure
    all values fall in a contiguous range starting at 0.

    Parameters
    ----------
    im : array_like
        An ND array containing greyscale values
    """
    im_flat = im.flatten()
    im_vals = sp.unique(im_flat)
    im_map = sp.zeros(shape=sp.amax(im_flat)+1)
    im_map[im_vals] = sp.arange(0, sp.size(sp.unique(im_flat)))
    im_new = im_map[im_flat]
    im_new = sp.reshape(im_new, newshape=sp.shape(im))
    im_new = sp.array(im_new, dtype=im_flat.dtype)
    return im_new

def find_edges(im, strel=None):
    r"""
    Find the edges between labelled regions in an image

    Parameters
    ----------
    im : array_like
        A 2D or 3D image containing regions with different labels

    strel : array_like
        The structuring element used to find the edges.  If ```None``` is
        provided (the default) the a round structure is used with a radius of
        1 voxel.
    """
    if strel == None:
        if im.ndim == 2:
            strel = disk(1)
        elif im.ndim == 3:
            strel = ball(1)
    temp = spim.convolve(input=im, weights=strel)/sp.sum(strel)
    temp = im != temp
    return temp

def get_border(shape, thickness=1, mode='edges'):
    r"""
    Creates an array of specified size with corners, edges or faces labelled as
    True.  This can be used as mask to manipulate values laying on the
    perimeter of an image.

    Parameters
    ----------
    shape : array_like
        The shape of the array to return.  Can be either 2D or 3D.

    thickness : scalar (default is 1)
        The number of pixels/voxels to place along perimeter.

    mode : string
        The type of border to create.  Options are 'faces', 'edges' (default)
        and 'corners'.  In 2D 'faces' and 'edges' give the same result.

    Returns
    -------
    An ND-array of specified shape with True values at the perimeter and False
    elsewhere.

    Examples
    --------
    >>> import scipy as sp
    >>> import porespy as ps
    >>> mask = ps.tools.get_border(shape=[3, 3], mode='corners')
    >>> print(mask)
    [[ True False  True]
     [False False False]
     [ True False  True]]
    >>> mask = ps.tools.get_border(shape=[3, 3], mode='edges')
    >>> print(mask)
    [[ True  True  True]
     [ True False  True]
     [ True  True  True]]
    """
    ndims = len(shape)
    t = thickness
    border = sp.ones(shape, dtype=bool)
    if mode == 'faces':
        if ndims == 2:
             border[t:-t, t:-t] = False
        if ndims == 3:
            border[t:-t, t:-t, t:-t] = False
    elif mode == 'edges':
        if ndims == 2:
            border[t:-t, t:-t] = False
        if ndims == 3:
            border[0::, t:-t, t:-t] = False
            border[t:-t, 0::, t:-t] = False
            border[t:-t, t:-t, 0::] = False
    elif mode == 'corners':
        if ndims == 2:
            border[t:-t, 0::] = False
            border[0::, t:-t] = False
        if ndims == 3:
            border[t:-t, 0::, 0::] = False
            border[0::, t:-t, 0::] = False
            border[0::, 0::, t:-t] = False
    return border

def fill_border(im, thickness=1, value=1):
    border = get_border(im, thickness=thickness)
    coords = sp.where(border)
    im[coords] = value
    return im

def get_dims(im):
    if im.ndim == 2:
        return 2
    if (im.ndim == 3) and (im.shape[2] == 1):
        return 2
    if im.ndim == 3:
        return 3

def rotate_image_and_repeat(im):
    # Find all markers in distance transform
    weighted_markers = sp.zeros_like(im, dtype=float)
    for phi in sp.arange(0, 45, 2):
        temp = spim.rotate(im.astype(int), angle=phi, order=5, mode='constant', cval=1)
        temp = get_weighted_markers(temp, Rs)
        temp = spim.rotate(temp.astype(int), angle=-phi, order=0, mode='constant', cval=0)
        X_lo = sp.floor(temp.shape[0]/2-im.shape[0]/2).astype(int)
        X_hi = sp.floor(temp.shape[0]/2+im.shape[0]/2).astype(int)
        weighted_markers += temp[X_lo:X_hi, X_lo:X_hi]
    return weighted_markers

def remove_isolated_voxels(im, conn=None):
    if im.ndim == 2:
        if conn == 4:
            strel = disk(1)
        elif conn in [None, 8]:
            strel = square(3)
    elif im.ndim == 3:
        if conn == 6:
            strel = ball(1)
        elif conn in [None, 26]:
            strel = cube(3)
    filtered_im = sp.copy(im)
    id_regions, num_ids = spim.label(filtered_im, structure=strel)
    id_sizes = sp.array(spim.sum(im, id_regions, range(num_ids + 1)))
    area_mask = (id_sizes == 1)
    filtered_im[area_mask[id_regions]] = 0
    return filtered_im