# Copyright (c) 2015-2020 by the parties listed in the AUTHORS file.
# All rights reserved.  Use of this source code is governed by
# a BSD-style license that can be found in the LICENSE file.

from collections.abc import MutableMapping, Sequence

import numpy as np

from .timing import function_timer


class Interval(object):
    """Class storing a single time and sample range.

    Args:
        start (float): The start time of the interval in seconds.
        stop (float): The stop time of the interval in seconds.
        first (int): The first sample index of the interval.
        last (int): The last sample index (inclusive) of the interval.

    """

    def __init__(self, start=None, stop=None, first=None, last=None):
        self._start = start
        self._stop = stop
        self._first = first
        self._last = last

    def __repr__(self):
        return "<Interval {} - {} [{}:{}]>".format(
            self._start, self._stop, self._first, self._last
        )

    def __eq__(self, other):
        if (
            (other.first == self.first)
            and (other.last == self.last)
            and np.isclose(other.start, self.start)
            and np.isclose(other.stop, self.stop)
        ):
            return True
        else:
            return False

    def __ne__(self, other):
        return not self.__eq__(other)

    @property
    def start(self):
        """(float): the start time of the interval."""
        if self._start is None:
            raise RuntimeError("Start time is not yet assigned")
        return self._start

    @start.setter
    def start(self, val):
        if val < 0.0:
            raise ValueError("Negative start time is not valid")
        self._start = val

    @property
    def stop(self):
        """(float): the start time of the interval."""
        if self._stop is None:
            raise RuntimeError("Stop time is not yet assigned")
        return self._stop

    @stop.setter
    def stop(self, val):
        if val < 0.0:
            raise ValueError("Negative stop time is not valid")
        self._stop = val

    @property
    def first(self):
        """(int): the first sample of the interval."""
        if self._first is None:
            raise RuntimeError("First sample is not yet assigned")
        return self._first

    @first.setter
    def first(self, val):
        if val < 0:
            raise ValueError("Negative first sample is not valid")
        self._first = val

    @property
    def last(self):
        """(int): the first sample of the interval."""
        if self._last is None:
            raise RuntimeError("Last sample is not yet assigned")
        return self._last

    @last.setter
    def last(self, val):
        if val < 0:
            raise ValueError("Negative last sample is not valid")
        self._last = val

    @property
    def range(self):
        """(float): the number seconds in the interval."""
        b = self.start
        e = self.stop
        return e - b

    @property
    def samples(self):
        """(int): the number samples in the interval."""
        b = self.first
        e = self.last
        return e - b + 1


# NOTE:  This class has basic (list-based) intersection and union support
# (__and__, __or__).  If we ever get so many intervals in a list that this is a
# performance bottleneck we could consider bringing in another external dependency on
# the intervaltree package for faster operations.  However, such a problem likely
# indicates that Intervals are not being used in their intended fashion (for fewer,
# larger spans of time).


class IntervalList(Sequence):
    """An list of Intervals which supports logical operations.

    Args:
        timestamps (array):  Array of sample times, required.
        intervals (list):  A list of Interval objects.
        timespans (list):  A list of tuples containing start and stop times.
        samplespans (list):  A list of tuples containing first and last (inclusive)
            sample ranges.

    """

    def __init__(self, timestamps, intervals=None, timespans=None, samplespans=None):
        self.timestamps = timestamps
        self._internal = None
        if intervals is not None:
            if timespans is not None or samplespans is not None:
                raise RuntimeError(
                    "If constructing from intervals, other spans should be None"
                )
            self._internal = list(intervals)
        else:
            if timespans is not None:
                if samplespans is not None:
                    raise RuntimeError(
                        "Cannot construct from both time and sample spans"
                    )
                if len(timespans) == 0:
                    self._internal = list()
                else:
                    # Construct intervals from time ranges
                    start_indx = np.searchsorted(
                        timestamps, [x[0] for x in timespans], side="left"
                    )
                    stop_indx = np.searchsorted(
                        timestamps, [x[1] for x in timespans], side="right"
                    )
                    stop_indx -= 1
                    self._internal = [
                        Interval(
                            start=timestamps[x[0]],
                            stop=timestamps[x[1]],
                            first=x[0],
                            last=x[1],
                        )
                        for x in zip(start_indx, stop_indx)
                    ]
            else:
                if samplespans is None:
                    raise RuntimeError(
                        "Must specify intervals, timespans, or samplespans"
                    )
                if len(samplespans) == 0:
                    self._internal = list()
                else:
                    # Construct intervals from sample ranges
                    self._internal = [
                        Interval(
                            start=timestamps[x[0]],
                            stop=timestamps[x[1]],
                            first=x[0],
                            last=x[1],
                        )
                        for x in samplespans
                    ]

    def __getitem__(self, key):
        return self._internal[key]

    def __contains__(self, item):
        for ival in self._internal:
            if ival == item:
                return True
        return False

    def __iter__(self):
        return iter(self._internal)

    def __len__(self):
        return len(self._internal)

    def __repr__(self):
        s = "["
        if len(self._internal) > 1:
            for it in self._internal[0:-1]:
                s += str(it)
                s += ", "
        if len(self._internal) > 0:
            s += str(self._internal[-1])
        s += "]"
        return s

    def __eq__(self, other):
        if len(self._internal) != len(other):
            return False
        if len(self.timestamps) != len(other.timestamps):
            return False
        if not np.isclose(self.timestamps[0], other.timestamps[0]) or not np.isclose(
            self.timestamps[-1], other.timestamps[-1]
        ):
            return False
        for s, o in zip(self._internal, other):
            if s != o:
                return False
        return True

    def __ne__(self, other):
        return not self.__eq__(other)

    def simplify(self):
        if len(self._internal) == 0:
            return
        propose = list()
        first = self._internal[0].first
        last = self._internal[0].last
        for i in range(1, len(self._internal)):
            cur_first = self._internal[i].first
            cur_last = self._internal[i].last
            if cur_first == last + 1:
                # This interval is contiguous with the previous one
                last = cur_last
            else:
                # There is a gap
                propose.append(
                    Interval(
                        first=first,
                        last=last,
                        start=self.timestamps[first],
                        stop=self.timestamps[last],
                    )
                )
                first = cur_first
                last = cur_last
        propose.append(
            Interval(
                first=first,
                last=last,
                start=self.timestamps[first],
                stop=self.timestamps[last],
            )
        )
        if len(propose) < len(self._internal):
            # Need to update
            self._internal = propose

    def __invert__(self):
        if len(self._internal) == 0:
            return
        neg = list()
        # Handle range before first interval
        if not np.isclose(self.timestamps[0], self._internal[0].start):
            last = self._internal[0].first - 1
            neg.append(
                Interval(
                    start=self.timestamps[0],
                    stop=self.timestamps[last],
                    first=0,
                    last=last,
                )
            )
        for i in range(len(self._internal) - 1):
            # Handle gaps between intervals
            cur_last = self._internal[i].last
            next_first = self._internal[i + 1].first
            if next_first != cur_last + 1:
                # There are some samples in between
                neg.append(
                    Interval(
                        start=self.timestamps[cur_last + 1],
                        stop=self.timestamps[next_first - 1],
                        first=cur_last + 1,
                        last=next_first - 1,
                    )
                )
        # Handle range after last interval
        if not np.isclose(self.timestamps[-1], self._internal[-1].stop):
            first = self._internal[-1].last + 1
            neg.append(
                Interval(
                    start=self.timestamps[first],
                    stop=self.timestamps[-1],
                    first=first,
                    last=len(self.timestamps) - 1,
                )
            )
        return IntervalList(self.timestamps, intervals=neg)

    def __and__(self, other):
        if len(self.timestamps) != len(other.timestamps):
            raise RuntimeError(
                "Cannot do AND operation on intervals with different timestamps"
            )
        if not np.isclose(self.timestamps[0], other.timestamps[0]) or not np.isclose(
            self.timestamps[-1], other.timestamps[-1]
        ):
            raise RuntimeError(
                "Cannot do AND operation on intervals with different timestamps"
            )
        if len(self._internal) == 0 or len(other) == 0:
            return IntervalList(self.timestamps, intervals=list())
        result = list()
        curself = 0
        curother = 0

        # Walk both sequences, building up the intersection.
        while (curself < len(self._internal)) and (curother < len(other)):
            low = max(self._internal[curself].first, other[curother].first)
            high = min(self._internal[curself].last, other[curother].last)
            if low <= high:
                result.append(
                    Interval(
                        first=low,
                        last=high,
                        start=self.timestamps[low],
                        stop=self.timestamps[high],
                    )
                )
            if self._internal[curself].last < other[curother].last:
                curself += 1
            else:
                curother += 1

        result = IntervalList(self.timestamps, intervals=result)
        result.simplify()
        return result

    def __or__(self, other):
        if len(self.timestamps) != len(other.timestamps):
            raise RuntimeError(
                "Cannot do OR operation on intervals with different timestamps"
            )
        if not np.isclose(self.timestamps[0], other.timestamps[0]) or not np.isclose(
            self.timestamps[-1], other.timestamps[-1]
        ):
            raise RuntimeError(
                "Cannot do OR operation on intervals with different timestamps"
            )
        if len(self._internal) == 0:
            return IntervalList(self.timestamps, intervals=other)
        elif len(other) == 0:
            return IntervalList(self.timestamps, intervals=self._internal)

        result = list()
        res_first = None
        res_last = None
        curself = 0
        curother = 0

        # Walk both sequences, building up the largest contiguous chunks possible.
        done_self = False
        done_other = False
        while (not done_self) or (not done_other):
            next = None
            if done_self:
                next = other[curother]
                curother += 1
            elif done_other:
                next = self._internal[curself]
                curself += 1
            else:
                if self._internal[curself].first < other[curother].first:
                    next = self._internal[curself]
                    curself += 1
                else:
                    next = other[curother]
                    curother += 1
            if curself >= len(self._internal):
                done_self = True
            if curother >= len(other):
                done_other = True

            if res_first is None:
                res_first = next.first
                res_last = next.last
            else:
                if next.first <= res_last + 1:
                    # We overlap last interval
                    if next.last > res_last:
                        # This interval extends beyond the last interval
                        res_last = next.last
                else:
                    # We have a break, close out previous interval and start a new one
                    result.append(
                        Interval(
                            first=res_first,
                            last=res_last,
                            start=self.timestamps[res_first],
                            stop=self.timestamps[res_last],
                        )
                    )
                    res_first = next.first
                    res_last = next.last
        # Close out final interval
        result.append(
            Interval(
                first=res_first,
                last=res_last,
                start=self.timestamps[res_first],
                stop=self.timestamps[res_last],
            )
        )

        result = IntervalList(self.timestamps, intervals=result)
        return result