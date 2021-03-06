# -*- coding: utf-8 -*-
'''
Support for Windows HyperV
'''

from __future__ import absolute_import

import json
import logging
import salt.utils
from salt.exceptions import CommandExecutionError, SaltInvocationError

log = logging.getLogger(__name__)

__virtualname__ = 'hyperv'

_SWITCH_TYPES = {
    0: 'external',
    1: 'internal',
    2: 'private'}


def __virtual__():
    '''
    Module load only if it on windows server
    '''
    if salt.utils.is_windows():
        return __virtualname__
    return False


def _has_powershell():
    '''
    Confirm if Powershell is available
    '''
    return 'powershell' in __salt__['cmd.run'](['where', 'powershell'],
                                               python_shell=False)


def _psrun(cmd, json_output=True):
    '''
    Run a powershell command
    '''

    if _has_powershell():
        if json_output:
            cmd = "%s | ConvertTo-Json -Depth 1 -Compress" % (cmd,)
        ret = __salt__['cmd.run_all'](cmd,
                                      shell='powershell',
                                      python_shell=False)
        if ret['retcode'] == 0:
            if json_output:
                if len(ret['stdout'].strip()) == 0:
                    # create an empty list if nothing is returned
                    ret['stdout'] = "[]"
                ret['stdout'] = json.loads(ret['stdout'])
                if not isinstance(ret['stdout'], list):
                    # if only one object is returned, append it to a list
                    ret['stdout'] = [ret['stdout']]
            return ret['stdout']
        else:
            raise CommandExecutionError(str(ret))


def install(with_gui=False):
    '''
    Install HyperV role and powershell administration tools.

    with_gui: False
        install GUI Adminstration tools too

    CLI EXample:

    .. code-block:: bash

        salt '*' hyperv.install
    '''
    features = ['Hyper-V', 'Hyper-V-Powershell']
    if with_gui is True:
        features.append('Hyper-V-Tools')

    return _psrun('Install-WindowsFeature %s' % (','.join(features),))


def vswitchs(**kwargs):
    '''
    Return a list of dictionary of information about all vSwitch on the minion

    CLI Example:

    .. code-block:: bash

        salt '*' hyperv.vswitchs
    '''
    switchs = []
    for switch in _psrun('Get-VMSwitch'):
        switchs.append({'name': switch['Name'],
                        'computername': switch['ComputerName'],
                        'type': switch['SwitchType'],
                        'netadapter': switch['NetAdapterInterfaceDescription']})
    return switchs


def add_vswitch(name, switchtype, **kwargs):
    '''
    Create a new vswitch

    CLI Example:

    .. code-block:: bash

        salt '*' hyperv.add_vswitch <name> private|internal
        salt '*' hyperv.add_vswitch <name> external interface=<interface>
    '''
    cmd = 'New-VMSwitch'
    if name is not None and len(name.strip()) > 0:
        cmd = '%s -Name %s' % (cmd, name)

        if switchtype is not None and len(switchtype.strip()) > 0:
            if switchtype not in _SWITCH_TYPES.values():
                raise SaltInvocationError(
                    'switchtype %s not supported' % (switchtype,))

            # external switch
            if switchtype == _SWITCH_TYPES[0]:
                if 'interface' not in kwargs:
                    raise SaltInvocationError(
                        'no interface name specified for external vswitch')
                cmd = '%s -NetAdapterName %s' % (cmd, kwargs['interface'])
            # internal or private switch
            elif switchtype in [_SWITCH_TYPES[1], _SWITCH_TYPES[2]]:
                cmd = '%s -SwitchType %s' % (cmd, switchtype)

            try:
                _psrun(cmd)
            except:
                return False
            else:
                return True
        else:
            raise SaltInvocationError('vswitch type not specified')
    else:
        raise SaltInvocationError('vswitch name not specified')


def remove_vswitch(name, **kwargs):
    '''
    Remove a vswitch

    CLI Example:

    .. code-block:: bash

        salt '*' hyperv.remove_vswitch <name>
    '''
    cmd = 'Remove-VMSwitch -Force'
    if name is not None and len(name.strip()) > 0:
        cmd = '%s -Name %s' % (cmd, name)

        try:
            _psrun(cmd)
        except:
            return False
        else:
            return True
    else:
        raise SaltInvocationError('vswitch name not specified')


def netadapters(all=False, **kwargs):
    '''
    Return a list of dictionary of physical network adapters

    all
        show all network adapters (included virtual one created by Hyper-V)

    CLI Example:

    .. code-block:: bash

        salt '*' hyperv.netadapters
        salt '*' hyperv.netadapters all=True
    '''
    args = ''
    if all is False:
        args = ' -Physical'

    adapters = []
    for adapter in _psrun('Get-NetAdapter%s' % (args,)):
        adapters.append({
            'name': adapter['Name'],
            'description': adapter['InterfaceDescription'],
            'mac': adapter['MacAddress']
        })
    return adapters


def set_netadapter(tgt, tgt_type='mac', **kwargs):
    '''
    Set configuration properties of a physical netadapter

    tgt
        unique identifier of the netadapter

    tgt_type : mac
        netadapter property used with ``tgt``

    name
        display name of netcard

    vlan
        VLAN ID

    CLI Example:

    .. code-block:: bash

        salt '*' hyperv.set_netadapter 00-00-00-00-00-00 name=vnic0
        salt '*' hyperv.set_netadapter 00-00-00-00-00-00 vlan=42
        salt '*' hyperv.set_netadapter 'Ethernet 5' tgt_type=name name=vnic0
    '''
    filter_properties = {'mac': 'MacAddress',
                         'name': 'Name'}
    if tgt_type not in filter_properties:
        raise SaltInvocationError('tgt_type %s is not allowed' % (tgt_type))

    get_cmd = 'Get-NetAdapter -Physical | Where {$_.%s -eq "%s"}' % (
        filter_properties[tgt_type],
        tgt)

    rename_cmd = None
    if 'name' in kwargs:
        rename_cmd = 'Rename-NetAdapter'
        rename_cmd = "%s -NewName %s -PassThru" % (rename_cmd, kwargs['name'])

    set_cmd = None
    if 'vlan' in kwargs:
        set_cmd = 'Set-NetAdapter'
        set_cmd = '%s -VlanID %s -PassThru' % (set_cmd, kwargs['vlan'])

    if rename_cmd is not None and set_cmd is not None:
        return _psrun("%s | %s | %s" % (get_cmd, rename_cmd, set_cmd))
    if rename_cmd is not None and set_cmd is None:
        return _psrun("%s | %s" % (get_cmd, rename_cmd))
    elif set_cmd is not None:
        return _psrun("%s | %s" % (get_cmd, set_cmd))
    else:
        return False


def vms(**kwargs):
    '''
    Return a list of dictionary of virtual machines

    CLI Example:

    .. code-block:: bash

        salt '*' hyperv.vms
    '''
    vms = []
    for vm in _psrun('Get-VM'):
        vms.append({
            'name': vm['Name'],
            'state': vm['State']})
    return vms


if __name__ == "__main__":
    __salt__ = ''

    import sys
    sys.exit(0)
