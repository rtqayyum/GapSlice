"""Independent py3gpp NR-LDPC coded-AWGN backend, not a full NR sidelink.

TS 38.212 channel coding/rate matching + Gray QAM + perfect-CSI AWGN.
No PSCCH/SCI decoding, DMRS estimation, resource pool, HARQ or channel measurement
is supplied by this adapter. RE overhead and fading remain declared models.
"""
import math
import numpy as np
from scipy.stats import beta
from gapslice.guard.phy import transport

MOD = {2:'QPSK',4:'16QAM',6:'64QAM'}


def demodulate(nr,received,mod,nvar):
    if mod!='64QAM':return nr.nrSymbolDemodulate(received,mod,nVar=nvar)
    # py3gpp 0.6.0 silently returns an empty vector for 64QAM. Use an explicit
    # max-log demapper, with the external modulator's exact Gray bit labeling.
    labels=((np.arange(64)[:,None] >> np.arange(5,-1,-1))&1).astype(int)
    constellation=nr.nrSymbolModulate(labels.reshape(-1),mod)
    distance=abs(np.asarray(received)[:,None]-constellation[None,:])**2
    llr=np.stack([(distance[:,labels[:,i]==1].min(axis=1)-distance[:,labels[:,i]==0].min(axis=1))/nvar for i in range(6)],axis=1)
    return llr.reshape(-1)


def prepare(prbs,payload,seed):
    import py3gpp as nr
    grant=transport(prbs,payload)
    if grant is None:raise ValueError('Infeasible transport block')
    A=grant['tbs_bits'];G=grant['data_re']*grant['modulation_order'];R=A/G
    info=nr.nrDLSCHInfo(A,R);mod=MOD[grant['modulation_order']]
    bits=np.random.default_rng(seed).integers(0,2,A,dtype=int)
    crc=nr.nrCRCEncode(bits,info['CRC'])
    segmented=nr.nrCodeBlockSegmentLDPC(crc,info['BGN'])
    coded=nr.nrLDPCEncode(segmented,info['BGN'])
    matched=nr.nrRateMatchLDPC(coded,G,0,mod,1)
    symbols=nr.nrSymbolModulate(matched,mod)
    return nr,grant,bits,symbols,mod,R,info


def frame(prbs,payload,snr_db,seed,noise=True):
    nr,grant,bits,symbols,mod,R,info=prepare(prbs,payload,seed)
    nvar=10**(-snr_db/10) if noise else 1e-8
    random=np.random.default_rng(np.random.SeedSequence([seed,4981]))
    received=symbols+math.sqrt(nvar/2)*(random.standard_normal(len(symbols))+1j*random.standard_normal(len(symbols))) if noise else symbols
    llr=demodulate(nr,received,mod,nvar)
    if llr.size!=grant['data_re']*grant['modulation_order']:raise RuntimeError('Invalid demapper output length')
    recovered=nr.nrRateRecoverLDPC(llr,len(bits),R,0,mod,1)
    decoded,_=nr.nrLDPCDecode(recovered,info['BGN'],12,Algorithm='Normalized min-sum')
    joined,block_error=nr.nrCodeBlockDesegmentLDPC(decoded,info['BGN'],len(bits)+info['L'])
    output,crc=nr.nrCRCDecode(joined,info['CRC'])
    return dict(failed=bool(block_error or np.any(crc) or not np.array_equal(output.reshape(-1),bits)),
                bit_errors=int(np.sum(output.reshape(-1)!=bits)),grant=grant,
                code_rate=R,ldpc_base_graph=int(info['BGN']))


def point(task):
    failures=0
    for i in range(task['frames']):
        failures+=frame(task['prbs'],task['payload'],task['snr_db'],task['seed']+i)['failed']
    n=task['frames'];upper=1. if failures==n else float(beta.ppf(.999,failures+1,n-failures))
    return dict(**task,failures=failures,upper=upper,
                backend='py3gpp 0.6.0; NR LDPC + rate matching + QAM + AWGN; 12 normalized-min-sum iterations')


class Lookup:
    def __init__(self,rows):
        self.curves={}
        for key in sorted({(x['prbs'],x['payload']) for x in rows}):
            rr=sorted([x for x in rows if (x['prbs'],x['payload'])==key],key=lambda x:x['snr_db'])
            if len(rr)<2:raise ValueError('Insufficient BLER grid')
            upper=np.maximum.accumulate(np.array([x['upper'] for x in rr])[::-1])[::-1]
            self.curves[key]=(np.array([x['snr_db'] for x in rr]),upper)

    def __call__(self,sinr,grant):
        key=(int(round((grant['data_re']+312)/126)),grant['payload_bytes'])
        # Invert the declared RE configuration, then check it exactly.
        if key not in self.curves or transport(*key)!=grant:raise ValueError('Missing/mismatched coded curve')
        grid,probability=self.curves[key];db=10*np.log10(np.maximum(sinr,1e-30))
        index=np.searchsorted(grid,db,side='right')-1
        return np.where(index<0,1.,probability[np.clip(index,0,len(grid)-1)])
