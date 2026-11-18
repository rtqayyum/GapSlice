"""Discrete transport accounting plus an explicitly uncalibrated PHY surrogate.

TBS/MCS arithmetic: ETSI TS 138 214 V16.14.0, 8.1.3 and 5.1.3.2, pinned
Release 16. Control/DMRS/SCI overheads below are declared configurations, not
an implementation of all legal NR configurations. SCI is not channel-coded
here. The Gaussian normal-approximation decoder is not LDPC/NR BLER validation.
"""
import math

import numpy as np
from scipy.special import ndtr


# Selected entries of TS 38.214 Table 5.1.3.1-1: (Qm, R * 1024).
MCS={0:(2,120), 4:(2,308), 9:(2,679), 14:(4,553), 20:(6,567), 24:(6,772), 28:(6,948)}
SMALL_TBS=(24,32,40,48,56,64,72,80,88,96,104,112,120,128,136,144,152,160,168,176,
    184,192,208,224,240,256,272,288,304,320,336,352,368,384,408,432,456,480,504,528,
    552,576,608,640,672,704,736,768,808,848,888,928,984,1032,1064,1128,1160,1192,1224,
    1256,1288,1320,1352,1416,1480,1544,1608,1672,1736,1800,1864,1928,2024,2088,2152,
    2216,2280,2408,2472,2536,2600,2664,2728,2792,2856,2976,3104,3240,3368,3496,3624,3752,3824)


def tbs(n_re, mcs):
    """Single-layer TBS in bits from an already deducted sidelink RE count."""
    if n_re <= 0 or mcs not in MCS:
        raise ValueError('Positive data RE count and supported MCS required')
    qm, r1024=MCS[mcs]
    rate=r1024/1024
    info=n_re*qm*rate
    if info <= 3824:
        step=2**max(3,math.floor(math.log2(info))-6)
        quantized=max(24,step*math.floor(info/step))
        return next(v for v in SMALL_TBS if v >= quantized)
    step=2**(math.floor(math.log2(info-24))-5)
    quantized=max(3840,step*math.floor((info-24)/step+.5))
    segments=(math.ceil((quantized+24)/3816) if rate <= .25 else
              math.ceil((quantized+24)/8424) if quantized > 8424 else 1)
    return int(8*segments*math.ceil((quantized+24)/(8*segments))-24)


def data_re(prbs, sidelink_symbols=14, dmrs_re_per_prb=18, x_overhead=0,
            psfch_symbols=0, pscch_re=240, sci2_re=72):
    """Configured net RE count; SCI2 and PSCCH costs include modeled occupancy."""
    if prbs < 10 or prbs % 10:
        raise ValueError('Prototype uses 10-PRB subchannels')
    result=(12*(sidelink_symbols-2-psfch_symbols)-dmrs_re_per_prb-x_overhead)*prbs-pscch_re-sci2_re
    if result <= 0:
        raise ValueError('No REs remain for payload')
    return result


def transport(prbs, payload_bytes=300, header_bytes=12):
    """Lowest selected MCS that fits this payload, including a declared header."""
    if not isinstance(payload_bytes,int) or payload_bytes<=0 or not isinstance(header_bytes,int) or header_bytes<0:
        raise ValueError('Require a positive integer payload and nonnegative integer header')
    re=data_re(prbs)
    for mcs in MCS:
        bits=tbs(re,mcs)
        if bits >= 8*(payload_bytes+header_bytes):
            return dict(data_re=re,mcs=mcs,tbs_bits=bits,payload_bytes=payload_bytes,
                        header_bytes=header_bytes,modulation_order=MCS[mcs][0])
    return None


def decode_error(sinr_linear, grant):
    """Uncalibrated finite-blocklength approximation, including TBS padding."""
    snr=np.maximum(np.asarray(sinr_linear),1e-15)
    n=grant['data_re']
    bits=grant['tbs_bits']+(16 if grant['tbs_bits'] <= 3824 else 24)
    capacity=np.minimum(np.log2(1+snr),grant['modulation_order'])
    dispersion=(1-(1+snr)**-2)*np.log2(np.e)**2
    return ndtr(-(n*capacity-bits+.5*np.log2(n))/np.sqrt(np.maximum(n*dispersion,1e-20)))
