# Copyright (c) 2015-2020 by the parties listed in the AUTHORS file.
# All rights reserved.  Use of this source code is governed by
# a BSD-style license that can be found in the LICENSE file.

from collections.abc import MutableMapping

from collections import OrderedDict

import re

import numpy as np

from .mpi import Comm

from .utils import Logger


class Data(MutableMapping):
    """Class which represents distributed data

    A Data object contains a list of observations assigned to
    each process group in the Comm.

    Args:
        comm (:class:`toast.Comm`):  The toast Comm class for distributing the data.
        view (bool):  If True, do not explicitly clear observation data on deletion.

    """

    def __init__(self, comm=Comm(), view=False):
        self._comm = comm
        self._view = view
        self.obs = []
        """The list of observations.
        """
        self._internal = dict()

    def __getitem__(self, key):
        return self._internal[key]

    def __delitem__(self, key):
        del self._internal[key]

    def __setitem__(self, key, value):
        self._internal[key] = value

    def __iter__(self):
        return iter(self._internal)

    def __len__(self):
        return len(self._internal)

    def __repr__(self):
        val = "<Data with {} Observations:\n".format(len(self.obs))
        for ob in self.obs:
            val += "{}\n".format(ob)
        val += "Metadata:\n"
        val += "{}".format(self._internal)
        val += "\n>"
        return val

    def __del__(self):
        if hasattr(self, "obs"):
            self.clear()

    @property
    def comm(self):
        """The toast.Comm over which the data is distributed."""
        return self._comm

    def clear(self):
        """Clear the list of observations."""
        if not self._view:
            for ob in self.obs:
                ob.clear()
        self.obs.clear()
        return

    def all_local_detectors(self, selection=None):
        """Get the superset of local detectors in all observations.

        This builds up the result from calling `select_local_detectors()` on
        all observations.

        Returns:
            (list):  The list of all local detectors across all observations.

        """
        all_dets = OrderedDict()
        for ob in self.obs:
            dets = ob.select_local_detectors(selection=selection)
            for d in dets:
                if d not in all_dets:
                    all_dets[d] = None
        return list(all_dets.keys())

    def info(self, handle=None):
        """Print information about the distributed data.

        Information is written to the specified file handle.  Only the rank 0
        process writes.

        Args:
            handle (descriptor):  file descriptor supporting the write()
                method.  If None, use print().

        Returns:
            None

        """
        # Each process group gathers their output

        groupstr = ""
        procstr = ""

        gcomm = self._comm.comm_group
        wcomm = self._comm.comm_world
        rcomm = self._comm.comm_group_rank

        if wcomm is None:
            msg = "Data distributed over a single process (no MPI)"
            if handle is None:
                print(msg, flush=True)
            else:
                handle.write(msg)
        else:
            if wcomm.rank == 0:
                msg = "Data distributed over {} processes in {} groups\n".format(
                    self._comm.world_size, self._comm.ngroups
                )
                if handle is None:
                    print(msg, flush=True)
                else:
                    handle.write(msg)

        def _get_optional(k, dt):
            if k in dt:
                return dt[k]
            else:
                return None

        for ob in self.obs:
            if self._comm.group_rank == 0:
                groupstr = "{}{}\n".format(groupstr, str(ob))

        # The world rank 0 process collects output from all groups and
        # writes to the handle

        recvgrp = ""
        if self._comm.world_rank == 0:
            if handle is None:
                print(groupstr, flush=True)
            else:
                handle.write(groupstr)
        if wcomm is not None:
            for g in range(1, self._comm.ngroups):
                if wcomm.rank == 0:
                    recvgrp = rcomm.recv(source=g, tag=g)
                    if handle is None:
                        print(recvgrp, flush=True)
                    else:
                        handle.write(recvgrp)
                elif g == self._comm.group:
                    if gcomm.rank == 0:
                        rcomm.send(groupstr, dest=0, tag=g)
                wcomm.barrier()
        return

    def split(
        self,
        obs_index=False,
        obs_name=False,
        obs_uid=False,
        obs_key=None,
        require_full=False,
    ):
        """Split the Data object.

        Create new Data objects that have views into unique subsets of the observations
        (the observations are not copied).  Only one "criteria" may be used to perform
        this splitting operation.  The observations may be split by index in the
        original list, by name, by UID, or by the value of a specified key.

        The new Data objects are returned in a dictionary whose keys are the value of
        the selection criteria (index, name, uid, or value of the key).  Any observation
        that cannot be place (because it is missing a name, uid or key) will be ignored
        and not added to any of the returned Data objects.  If the `require_full`
        parameter is set to True, such situations will raise an exception.

        Args:
            obs_index (bool):  If True, split by index in original list of observations.
            obs_name (bool):  If True, split by observation name.
            obs_uid (bool):  If True, split by observation UID.
            obs_key (str):  Split by values of this observation key.

        Returns:
            (OrderedDict):  The dictionary of new Data objects.

        """
        log = Logger.get()
        check = int(obs_index) + int(obs_name) + int(obs_uid) + int(obs_key is not None)
        if check == 0 or check > 1:
            raise RuntimeError("You must specify exactly one split criteria")

        datasplit = OrderedDict()

        group_rank = self.comm.group_rank
        group_comm = self.comm.comm_group

        if obs_index:
            # Splitting by index
            for iob, ob in enumerate(self.obs):
                newdat = Data(comm=self._comm, view=True)
                newdat._internal = self._internal
                newdat.obs.append(ob)
                datasplit[iob] = newdat
        elif obs_name:
            # Splitting by name
            for iob, ob in enumerate(self.obs):
                if ob.name is None:
                    if require_full:
                        msg = f"require_full is True, but observation {iob} has no name"
                        log.error_rank(msg, comm=group_comm)
                        raise RuntimeError(msg)
                else:
                    newdat = Data(comm=self._comm, view=True)
                    newdat._internal = self._internal
                    newdat.obs.append(ob)
                    datasplit[ob.name] = newdat
        elif obs_uid:
            # Splitting by UID
            for iob, ob in enumerate(self.obs):
                if ob.uid is None:
                    if require_full:
                        msg = f"require_full is True, but observation {iob} has no UID"
                        log.error_rank(msg, comm=group_comm)
                        raise RuntimeError(msg)
                else:
                    newdat = Data(comm=self._comm, view=True)
                    newdat._internal = self._internal
                    newdat.obs.append(ob)
                    datasplit[ob.uid] = newdat
        elif obs_key is not None:
            # Splitting by arbitrary key.  Unlike name / uid which are built it to the
            # observation class, arbitrary keys might be modified in different ways
            # across all processes in a group.  For this reason, we do an additional
            # check for consistent values across the process group.
            for iob, ob in enumerate(self.obs):
                if obs_key not in ob:
                    if require_full:
                        msg = f"require_full is True, but observation {iob} has no key '{obs_key}'"
                        log.error_rank(msg, comm=group_comm)
                        raise RuntimeError(msg)
                else:
                    obs_val = ob[obs_key]
                    # Get the values from all processes in the group
                    group_vals = None
                    if group_comm is None:
                        group_vals = [obs_val]
                    else:
                        group_vals = group_comm.allgather(obs_val)
                    if group_vals.count(group_vals[0]) != len(group_vals):
                        msg = f"observation {iob}, key '{obs_key}' has inconsistent values across processes"
                        log.error_rank(msg, comm=group_comm)
                        raise RuntimeError(msg)
                    if obs_val not in datasplit:
                        newdat = Data(comm=self._comm, view=True)
                        newdat._internal = self._internal
                        datasplit[obs_val] = newdat
                    datasplit[obs_val].obs.append(ob)
        return datasplit

    def select(
        self, obs_index=None, obs_name=None, obs_uid=None, obs_key=None, obs_val=None
    ):
        """Create a new Data object with a subset of observations.

        The returned Data object just has a view of the original observations (they
        are not copied).

        The list of observations in the new Data object is a logical OR of the
        criteria passed in:
            * Index location in the original list of observations
            * Name of the observation
            * UID of the observation
            * Existence of the specified dictionary key
            * Required value of the specified dictionary key

        Args:
            obs_index (int):  Observation location in the original list.
            obs_name (str):  The observation name or a compiled regular expression
                object to use for matching.
            obs_uid (int):  The observation UID to select.
            obs_key (str):  The observation dictionary key to examine.
            obs_val (str):  The required value of the observation dictionary key or a
                compiled regular expression object to use for matching.

        Returns:
            (Data):  A new Data object with references to the orginal metadata and
                a subset of observations.

        """
        log = Logger.get()
        if obs_val is not None and obs_key is None:
            raise RuntimeError("If you specify obs_val, you must also specify obs_key")

        group_rank = self.comm.group_rank
        group_comm = self.comm.comm_group

        new_data = Data(comm=self._comm, view=True)

        # Use a reference to the original metadata
        new_data._internal = self._internal

        for iob, ob in enumerate(self.obs):
            if obs_index is not None and obs_index == iob:
                new_data.obs.append(ob)
            if obs_name is not None and ob.name is not None:
                if isinstance(obs_name, re.Pattern):
                    if obs_name.match(ob.name) is not None:
                        new_data.obs.append(ob)
                elif obs_name == ob.name:
                    new_data.obs.append(ob)
            if obs_uid is not None and ob.uid is not None and obs_uid == ob.uid:
                new_data.obs.append(ob)
            if obs_key is not None and obs_key in ob:
                # Get the values from all processes in the group and check
                # for consistency.
                group_vals = None
                if group_comm is None:
                    group_vals = [ob[obs_key]]
                else:
                    group_vals = group_comm.allgather(ob[obs_key])
                if group_vals.count(group_vals[0]) != len(group_vals):
                    msg = f"observation {iob}, key '{obs_key}' has inconsistent values across processes"
                    log.error_rank(msg, comm=group_comm)
                    raise RuntimeError(msg)

                if obs_val is None:
                    # We have the key, and are accepting any value
                    new_data.obs.append(ob)
                elif isinstance(obs_val, re.Pattern):
                    if obs_val.match(ob[obs_key]) is not None:
                        # Matches our regex
                        new_data.obs.append(ob)
                elif obs_val == ob[obs_key]:
                    new_data.obs.append(ob)
        return new_data