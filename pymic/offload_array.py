# Copyright (c) 2014-2015, Intel Corporation All rights reserved. 
# 
# Redistribution and use in source and binary forms, with or without 
# modification, are permitted provided that the following conditions are 
# met: 
# 
# 1. Redistributions of source code must retain the above copyright 
# notice, this list of conditions and the following disclaimer. 
#
# 2. Redistributions in binary form must reproduce the above copyright 
# notice, this list of conditions and the following disclaimer in the 
# documentation and/or other materials provided with the distribution. 
#
# 3. Neither the name of the copyright holder nor the names of its 
# contributors may be used to endorse or promote products derived from 
# this software without specific prior written permission. 
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS 
# IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED 
# TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A 
# PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT 
# HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, 
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED 
# TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR 
# PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF 
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING 
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS 
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE. 

from __future__ import print_function

import numpy 

from _misc import _debug as debug
from _misc import _deprecated as deprecated
from _tracing import _trace as trace
from _misc import _map_data_types as map_data_types

from offload_device import OffloadDevice
from offload_device import devices

# TODO:
#   - find out how to easily copy the whole numpy.array interface


_offload_libraries = {}
for d in devices:
    if d is not any:
        dev = devices[d]
        _offload_libraries[d] = dev.load_library("liboffload_array.so")

    
class OffloadArray(object):
    """An offloadable array structure to perform array-based computation
       on an Intel(R) Xeon Phi(tm) Coprocessor
       
       The interface is largely numpy-alike.  All operators execute their
       respective operation in an element-wise fashion on the target device.
    """   
    
    array = None
    device = None
    stream = None
    _library = None
    
    def __init__(self, shape, dtype, order="C", 
                 alloc_arr=True, base=None, device=None, stream=None):
        # allocate the array on the coprocessor
        self.order = order
        self.dtype = numpy.dtype(dtype)
        self.base = base
    
        # save a reference to the device
        assert device is not None
        assert stream is not None
        self.device = device
        self.stream = stream
    
        # determine size of the array from its shape
        try:
            size = 1
            for d in shape:
                size *= d
        except TypeError:
            assert isinstance(shape, (int, long))
            size = shape
            shape = (shape,)
        self.size = size
        self.shape = shape
        self.nbytes = self.dtype.itemsize * self.size
        
        if base is not None:
            self.array = base.array.reshape(shape)
        else:
            if alloc_arr:
                if stream is None:
                    stream = self.stream
                self.array = numpy.empty(self.shape, self.dtype, self.order)
                stream._buffer_allocate(self.array)

        self._library = _offload_libraries[device.device_id]
        
    def __del__(self):
        # deallocate storage in the target if this array goes away
        if self.base is None:
            self.stream._buffer_release(self.array)
        
    def __str__(self):
        return str(self.array)
    
    def __repr__(self):
        return repr(self.array)
    
    def __hash__(self):
        raise TypeError("An OffloadArray is not hashable.")
    
    @trace
    def update_device(self):
        """Update the OffloadArray's buffer space on the associated
           device by copying the contents of the associated numpy.ndarray 
           to the device.
        
           Parameters
           ----------
           n/a
           
           Returns
           -------
           out : OffloadArray
               The object instance of this OffloadArray.
           
           See Also
           --------
           update_host     
        """
        self.stream._buffer_update_on_target(self.array)
        return None
    
    @trace
    def update_host(self):
        """Update the associated numpy.ndarray on the host with the contents
           by copying the OffloadArray's buffer space from the device to the
           host.

           Parameters
           ----------
           n/a 
            
           Returns
           -------
           out : OffloadArray
               The object instance of this OffloadArray.
           
           See Also
           --------
           update_device
        """
        self.stream._buffer_update_on_host(self.array)
        return self
    
    def assign_stream(self, stream):
        """Assign a new stream for this OffloadArray's operations
           (update_device, update_host, __add__, etc.).
        
           Parameters
           ----------
           stream : OffloadStream
               New default stream.
            
           Returns
           -------
           n/a

           See Also
           --------
           n/a
        """    
        if stream.get_device() is not self.device:
            raise ValueError("Cannot assign a stream from different device "
                             "({0} != {1})".format(self.device, 
                                                   stream.get_device()))
        self.stream = stream
    
    def __add__(self, other):
        """Add an array or scalar to an array."""

        dt = map_data_types(self.dtype)
        n = int(self.size)
        x = self.array
        incx = int(1)
        if isinstance(other, OffloadArray):
            if self.array.shape != other.array.shape:
                raise ValueError("shapes of the arrays need to match: "
                                 "{0} != {1}".format(self.array.shape, 
                                                     other.shape))
            if self.dtype != other.dtype:
                raise ValueError("Data types do not match: "
                                 "{0} != {1}".format(self.dtype, other.dtype))
            y = other.array
            incy = int(1)
            incr = int(1)
        elif isinstance(other, numpy.ndarray):
            if self.array.shape != other.shape:
                raise ValueError("shapes of the arrays need to match: "
                                 "{0} != {1}".format(self.array.shape, 
                                                     other.shape))
            if self.dtype != other.dtype:
                raise ValueError("Data types do not match: "
                                 "{0} != {1}".format(self.dtype, other.dtype))
            y = other
            incy = int(1)
            incr = int(1)
        else:
            # scalar
            if self.dtype != type(other):
                raise ValueError("Data types do not match: "
                                 "{0} != {1}".format(self.dtype, type(other)))
            y = other
            incy = int(0)
            incr = int(1)
        result = OffloadArray(self.shape, self.dtype, device=self.device, 
                              stream=self.stream)
        self.stream.invoke(self._library.pymic_offload_array_add,
                           dt, n, x, incx, y, incy, result.array, incr)
        return result

    def __sub__(self, other):
        """Subtract an array or scalar from an array."""
        
        dt = map_data_types(self.dtype)
        n = int(self.size)
        x = self.array
        incx = int(1)
        if isinstance(other, OffloadArray):
            if self.array.shape != other.array.shape:
                raise ValueError("shapes of the arrays need to match: "
                                 "{0} != {1}".format(self.array.shape, 
                                                     other.shape))
            if self.dtype != other.dtype:
                raise ValueError("Data types do not match: "
                                 "{0} != {1}".format(self.dtype, other.dtype))
            y = other.array
            incy = int(1)
            incr = int(1)
        elif isinstance(other, numpy.ndarray):
            if self.array.shape != other.shape:
                raise ValueError("shapes of the arrays need to match: "
                                 "{0} != {1}".format(self.array.shape, 
                                                     other.shape))
            if self.dtype != other.dtype:
                raise ValueError("Data types do not match: "
                                 "{0} != {1}".format(self.dtype, other.dtype))
            y = other
            incy = int(1)
            incr = int(1)
        else:
            # scalar
            if self.dtype != type(other):
                raise ValueError("Data types do not match: "
                                 "{0} != {1}".format(self.dtype, type(other)))
            y = other
            incy = int(0)
            incr = int(1)
        result = OffloadArray(self.shape, self.dtype, device=self.device, 
                              stream=self.stream)
        self.stream.invoke(self._library.pymic_offload_array_sub,
                           dt, n, x, incx, y, incy, result.array, incr)
        return result

    def __mul__(self, other):
        """Multiply an array or a scalar with an array."""

        dt = map_data_types(self.dtype)
        n = int(self.size)
        x = self.array
        incx = int(1)
        if isinstance(other, OffloadArray):
            if self.array.shape != other.array.shape:
                raise ValueError("shapes of the arrays need to match: "
                                 "{0} != {1}".format(self.array.shape, 
                                                     other.shape))
            if self.dtype != other.dtype:
                raise ValueError("Data types do not match: "
                                 "{0} != {1}".format(self.dtype, other.dtype))
            y = other.array
            incy = int(1)
            incr = int(1)
        elif isinstance(other, numpy.ndarray):
            if self.array.shape != other.shape:
                raise ValueError("shapes of the arrays need to match: "
                                 "{0} != {1}".format(self.array.shape, 
                                                     other.shape))
            if self.dtype != other.dtype:
                raise ValueError("Data types do not match: "
                                 "{0} != {1}".format(self.dtype, other.dtype))
            y = other
            incy = int(1)
            incr = int(1)
        else:
            # scalar
            if self.dtype != type(other):
                raise ValueError("Data types do not match: "
                                 "{0} != {1}".format(self.dtype, type(other)))
            y = other
            incy = int(0)
            incr = int(1)
        result = OffloadArray(self.shape, self.dtype, device=self.device, 
                              stream=self.stream)
        self.stream.invoke(self._library.pymic_offload_array_mul,
                           dt, n, x, incx, y, incy, result.array, incr)
        return result

    def fill(self, value):
        """Fill an array with the specified value.
           
           Parameters
           ----------
           value : type
               Value to fill the array with.
            
           Returns
           -------
           out : OffloadArray
               The object instance of this OffloadArray.
           
           See Also
           --------
           zero
        """
        if self.dtype != type(value):
            raise ValueError("Data type do not match: "
                             "{0} != {1}".format(self.dtype, type(value)))

        dt = map_data_types(self.dtype)
        n = int(self.size)
        x = self

        self.stream.invoke(self._library.pymic_offload_array_fill, 
                           dt, n, x, value)
        return self    
    
    def fillfrom(self, array):
        """Fill an array from a numpy.ndarray."""
        
        if not isinstance(array, numpy.ndarray):
            raise TypeError("only numpy.ndarray supported")
        
        if self.shape != array.shape:
            raise TypeError("shapes of arrays to not match")

        # update the host part of the buffer and then update the device
        self.array[:] = array[:]
        self.update_device()
        
        return self
    
    def zero(self, zero_value=None):
        """Fill the array with zeros.
           
           Parameters
           ----------
           n/a 
            
           Returns
           -------
           out : OffloadArray
               The object instance of this OffloadArray.
           
           See Also
           --------
           fill
        """
        if zero_value is None:
            if self.dtype == int:
                zero_value = 0
            elif self.dtype == float:
                zero_value = 0.0
            elif self.dtype == complex:
                zero_value = complex(0.0, 0.0)
            else:
                raise ValueError("Do not know representation of zero "
                                 "for type {0}".format(self.dtype))
        return self.fill(zero_value)
    
    def one(self, one_value=None):
        """Fill the array with ones.
           
           Parameters
           ----------
           n/a 
            
           Returns
           -------
           out : OffloadArray
               The object instance of this OffloadArray.
           
           See Also
           --------
           fill
        """
        if one_value is None:
            if self.dtype == int:
                one_value = 1
            elif self.dtype == float:
                one_value = 1.0
            elif self.dtype == complex:
                one_value = complex(1.0, 0.0)
            else:
                raise ValueError("Do not know representation of one "
                                 "for type {0}".format(dtype))
        return self.fill(one_value)
    
    def __len__(self):
        """Return the of size of the leading dimension."""
        if len(self.shape):
            return self.shape[0]
        else:
            return 1
        
    def __abs__(self):
        """Return a new OffloadArray with the absolute values of the elements 
           of `self`."""
        
        dt = map_data_types(self.dtype)
        n = int(self.array.size)
        x = self.array
        if dt == 2:  # complex data
            result = self.stream.empty(self.shape, dtype=numpy.float, 
                                       order=self.order, update_host=False)
        else:
            result = self.stream.empty_like(self, update_host=False)
        self.stream.invoke(self._library.pymic_offload_array_abs, 
                           dt, n, x, result)
        return result
        
    def __pow__(self, other):
        """Element-wise pow() function."""
        
        dt = map_data_types(self.dtype)
        n = int(self.size)
        x = self.array
        incx = int(1)
        if isinstance(other, OffloadArray):
            if self.array.shape != other.array.shape:
                raise ValueError("shapes of the arrays need to match ("
                                 + str(self.array.shape) + " != " 
                                 + str(other.array.shape) + ")")
            if self.dtype != other.dtype:
                raise ValueError("Data types do not match: "
                                 "{0} != {1}".format(self.dtype, other.dtype))
            y = other.array
            incy = int(1)
            incr = int(1)
        elif isinstance(other, numpy.ndarray):
            if self.array.shape != other.shape:
                raise ValueError("shapes of the arrays need to match ("
                                 + str(self.array.shape) + " != "
                                 + str(other.shape) + ")")
            if self.dtype != other.dtype:
                raise ValueError("Data types do not match: "
                                 "{0} != {1}".format(self.dtype, other.dtype))
            y = other
            incy = int(1)
            incr = int(1)
        else:
            # scalar
            if self.dtype != type(other):
                raise ValueError("Data types do not match: "
                                 "{0} != {1}".format(self.dtype, type(other)))
            y = other
            incy = int(0)
            incr = int(1)
        result = OffloadArray(self.shape, self.dtype, device=self.device, 
                              stream=self.stream)
        self.stream.invoke(self._library.pymic_offload_array_pow,
                           dt, n, x, incx, y, incy, result.array, incr)
        return result
        
    def reverse(self):
        """Return a new OffloadArray with all elements in reverse order."""
        
        if len(self.shape) > 1:
            raise ValueError("Multi-dimensional arrays cannot be revered.")
        
        dt = map_data_types(self.dtype)
        n = int(self.array.size)
        result = self.stream.empty_like(self)
        self.stream.invoke(self._library.pymic_offload_array_reverse,
                           dt, n, self, result)
        return result

    def reshape(self, *shape):
        """Assigns a new shape to an existing OffloadArray without changing
           the data of it."""
        
        if isinstance(shape[0], tuple) or isinstance(shape[0], list):
            shape = tuple(shape[0])
        # determine size of the array from its shape
        try:
            size = 1
            for d in shape:
                size *= d
        except TypeError:
            assert isinstance(shape, (int, long, numpy.integer))
            size = shape
            shape = (shape,)
        if size != self.size:
            raise ValueError("total size of reshaped array must be unchanged")
        return OffloadArray(shape, self.dtype, self.order,
                            False, self, device=self.device)

    def ravel(self):
        """Return a flattened array."""
        return self.reshape(self.size)

    def __setslice__(self, i, j, sequence):
        """Overwrite this OffloadArray with slice coming from another array."""
        # TODO: raise errors here: shape/size/data data type

        lb = min(i, self.size)
        ub = min(j, self.size)
        dt = map_data_types(self.dtype)

        if isinstance(sequence, OffloadArray):
            self.stream.invoke(self._library.pymic_offload_array_setslice, 
                               dt, lb, ub, self, sequence)
        elif isinstance(sequence, numpy.ndarray):
            offl_sequence = self.stream.bind(sequence)
            self.stream.invoke(self._library.pymic_offload_array_setslice, 
                               dt, lb, ub, self, offl_sequence)
        else:
            self.fill(sequence)