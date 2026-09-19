"""Numerical verification of staggered 1-D linear acoustics against a plane wave.

This periodic manufactured solution verifies propagation, not a speaker or flame.
Pressure p_t=-rho*c^2*u_x; velocity u_t=-p_x/rho.
"""
from pathlib import Path
import numpy as np
from .intake import json_write


def plane_wave(cells=128, cycles=1., courant=.5, length_m=5.716666666666667,
               sound_speed_m_s=343., density_kg_m3=1.204, amplitude_Pa=1.):
    if type(cells) is not int or not 16 <= cells <= 4096:
        raise ValueError('cells must be integer 16..4096')
    if not all(np.isfinite(v) and v > 0 for v in (cycles, courant, length_m, sound_speed_m_s, density_kg_m3, amplitude_Pa)) or courant > 1:
        raise ValueError('positive physical inputs and CFL <=1 required')
    if cycles > 10:
        raise ValueError('bounded verification cycles <=10')
    c, rho, dx = sound_speed_m_s, density_kg_m3, length_m/cells
    end = cycles * length_m/c
    steps = int(np.ceil(end/(courant*dx/c)))
    dt = end/steps
    x = np.arange(cells)*dx
    k = 2*np.pi/length_m
    p = amplitude_Pa*np.sin(k*x)
    u = amplitude_Pa/(rho*c)*np.sin(k*(x+dx/2+c*dt/2))
    frames = []
    stride = max(1, steps//32)
    for n in range(steps):
        u -= dt/(rho*dx)*(np.roll(p,-1)-p)
        p -= rho*c*c*dt/dx*(u-np.roll(u,1))
        if (n+1)%stride==0 or n==steps-1:
            frames.append({'time_s': (n+1)*dt, 'pressure_Pa':p.tolist()})
    exact = amplitude_Pa*np.sin(k*(x-c*end))
    return {'cells':cells,'dx_m':dx,'dt_s':dt,'frequency_hz':c/length_m,
            'relative_L2':float(np.linalg.norm(p-exact)/np.linalg.norm(exact)),
            'pressure_rms_Pa':float(np.sqrt(np.mean(p*p))),
            'expected_pressure_rms_Pa':amplitude_Pa/np.sqrt(2),
            'x_m':x.tolist(),'pressure_Pa':p.tolist(),'analytic_pressure_Pa':exact.tolist(),
            'frames':frames,'boundary':'periodic','evidence_type':'numerical_verification',
            'scope':'1D linear plane wave; no speaker geometry, near-field airflow, or flame response'}


def verification(output_dir):
    results=[plane_wave(n) for n in (64,128,256)]
    temporal=[plane_wave(256,courant=c) for c in (.8,.4,.2)]
    errors=[r['relative_L2'] for r in results]
    rates=[float(np.log(errors[i]/errors[i+1])/np.log(2)) for i in (0,1)]
    result={'status':'passed' if min(rates)>1.8 and errors[-1]<.002 else 'failed',
            'criterion':{'minimum_observed_order':1.8,'fine_relative_L2_max':.002},
            'meshes':results,'observed_order':rates,'time_step_study':temporal,
            'temporal_note':'Spatial and temporal dispersion may cancel; decreasing CFL alone need not reduce total error.',
            'physical_validation':'not experimental speaker validation'}
    json_write(Path(output_dir)/'acoustic_verification.json',result)
    return result
