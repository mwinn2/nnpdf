"""
    This module defines custom base layers to be used by the n3fit
    Neural Network.
    These layers can use the keras standard set of activation function
    or implement their own.

    For a layer to be used by n3fit it should be contained in the `layers` dictionary defined below.
    This dictionary has the following structure:

        'name of the layer' : ( Layer_class, {dictionary of arguments: defaults} )

    In order to add custom activation functions, they must be added to
    the `custom_activations` dictionary with the following structure:

        'name of the activation' : function

    The names of the layer and the activation function are the ones to be used in the n3fit runcard.
"""

from keras.layers import Dense as KerasDense
from keras.layers import Dropout, Lambda
from keras.layers import Input  # pylint: disable=unused-import
from keras.layers import LSTM, Concatenate
from keras.regularizers import l1_l2

from . import operations as ops
from .MetaLayer import MetaLayer

# Custom activation functions
def square_activation(x):
    """Squares the input"""
    return x * x


def square_singlet(x):
    """Square the singlet sector
    Defined as the two first values of the NN"""
    singlet_squared = x[..., :2] ** 2
    return ops.concatenate([singlet_squared, x[..., 2:]], axis=-1)


def modified_tanh(x):
    """A non-saturating version of the tanh function"""
    return ops.absolute(x) * ops.tanh(x)


def leaky_relu(x):
    """Computes the Leaky ReLU activation function"""
    return ops.leaky_relu(x, alpha=0.2)


custom_activations = {
    "square": square_activation,
    "square_singlet": square_singlet,
    "leaky_relu": leaky_relu,
    "modified_tanh": modified_tanh,
}


def LSTM_modified(**kwargs):
    """
    LSTM asks for a sample X timestep X features kind of thing so we need to reshape the input
    """
    the_lstm = LSTM(**kwargs)
    ExpandDim = Lambda(lambda x: ops.expand_dims(x, axis=-1))

    def ReshapedLSTM(input_tensor):
        if len(input_tensor.shape) == 2:
            reshaped = ExpandDim(input_tensor)
            return the_lstm(reshaped)
        else:
            return the_lstm(input_tensor)

    return ReshapedLSTM


class Dense(KerasDense, MetaLayer):
    pass


def dense_per_flavour(basis_size=8, kernel_initializer="glorot_normal", **dense_kwargs):
    """
    Generates a list of layers which can take as an input either one single layer
    or a list of the same size
    If taking one single layer, this one single layer will be the input of every layer in the list.
    If taking a list of layer of the same size, each layer on the list will take
    as input the layer on the input list in the same position.

    Note that, if the initializer is seeded, it should be a list where the seed is different
    for each element.

    i.e., if `basis_size` is 3 and is taking as input one layer A the output will be:
        [B1(A), B2(A), B3(A)]
    if taking, instead, a list [A1, A2, A3] the output will be:
        [B1(A1), B2(A2), B3(A3)]
    """
    if isinstance(kernel_initializer, str):
        kernel_initializer = basis_size * [kernel_initializer]

    # Need to generate a list of dense layers
    dense_basis = [
        base_layer_selector("dense", kernel_initializer=initializer, **dense_kwargs)
        for initializer in kernel_initializer
    ]

    def apply_dense(xinput):
        """
        The input can be either one single layer or a list of layers of
        length `basis_size`

        If taking one single layer, this one single layer will be the input of every
        layer in the list.
        If taking a list of layer of the same size, each layer on the list will take
        as input the layer on the input list in the same position.
        """
        if isinstance(xinput, (list, tuple)):
            if len(xinput) != basis_size:
                raise ValueError(
                    f"""The input of the dense_per_flavour and the basis_size
doesn't match, got a list of length {len(xinput)} for a basis_size of {basis_size}"""
                )
            results = [dens(ilayer) for dens, ilayer in zip(dense_basis, xinput)]
        else:
            results = [dens(xinput) for dens in dense_basis]

        return results

    return apply_dense


layers = {
    "dense": (
        Dense,
        {
            "kernel_initializer": "glorot_normal",
            "units": 5,
            "activation": "sigmoid",
            "kernel_regularizer": None,
        },
    ),
    "dense_per_flavour": (
        dense_per_flavour,
        {
            "kernel_initializer": "glorot_normal",
            "units": 5,
            "activation": "sigmoid",
            "basis_size": 8,
        },
    ),
    "LSTM": (
        LSTM_modified,
        {"kernel_initializer": "glorot_normal", "units": 5, "activation": "sigmoid"},
    ),
    "dropout": (Dropout, {"rate": 0.0}),
    "concatenate": (Concatenate, {}),
}

regularizers = {'l1_l2': (l1_l2, {'l1': 0.0, 'l2': 0.0})}


def base_layer_selector(layer_name, **kwargs):
    """
    Given a layer name, looks for it in the `layers` dictionary and returns an instance.

    The layer dictionary defines a number of defaults
    but they can be overwritten/enhanced through kwargs

    Parameters
    ----------
        `layer_name
            str with the name of the layer
        `**kwargs`
            extra optional arguments to pass to the layer (beyond their defaults)
    """
    try:
        layer_tuple = layers[layer_name]
    except KeyError as e:
        raise NotImplementedError(
            f"Layer not implemented in keras_backend/base_layers.py: {layer_name}"
        ) from e

    layer_class = layer_tuple[0]
    layer_args = layer_tuple[1]

    for key, value in kwargs.items():
        # Check whether the activation function is a custom one
        if key == "activation":
            value = custom_activations.get(value, value)
        if key in layer_args.keys():
            layer_args[key] = value
        if key == "name":
            layer_args[key] = value

    return layer_class(**layer_args)


def regularizer_selector(reg_name, **kwargs):
    """Given a regularizer name looks in the `regularizer` dictionary and
    return an instance.

    The regularizer dictionary defines defaults for regularizers but these can
    be overwritten by supplying kwargs

    Parameters
    ----------
    layer_name
        str with the name of the regularizer
    **kwargs
        extra optional arguments to pass to the regularizer

    """
    if reg_name is None:
        return None

    try:
        reg_tuple = regularizers[reg_name]
    except KeyError:
        raise NotImplementedError(
            f"Regularizer not implemented in keras_backend/base_layers.py: {reg_name}"
        )

    reg_class = reg_tuple[0]
    reg_args = reg_tuple[1]

    for key, value in kwargs.items():
        if key in reg_args.keys():
            reg_args[key] = value

    return reg_class(**reg_args)
