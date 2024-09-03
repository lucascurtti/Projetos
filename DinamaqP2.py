pip install git+https://github.com/petrobras/ross.git
import ross as rs
import numpy as np
from ross.units import Q_

# Criando o Material (Aço)
steel = rs.Material(name="Steel", rho=7810, E=210e9, Poisson=0.3)
steel.save_material()

# Modelando o eixo (com 6 elementos)
shaft_elem = [
    rs.ShaftElement(
        L=1.0,              # Comprimento de 1 metro para cada elemento
        idl=0.05,           # Diâmetro interno de 5 cm
        odl=0.1,            # Diâmetro externo de 10 cm
        material=steel,
        shear_effects=True,
        rotary_inertia=True,
        gyroscopic=True,
    )
    for _ in range(6)         # 6 elementos para um eixo total de 6 metros
]

# Modelando o disco (pás)
disk0 = rs.DiskElement.from_geometry(
    n=2, material=steel, width=0.2, i_d=0.05, o_d=1.5  # Disco com 20 cm de largura e 1.5 metros de diâmetro externo
)

disks = [disk0]

# Modelando os mancais (suporte de 1 milhão de N/m)
stfx = 1e6
stfy = 1e6

bearing0 = rs.BearingElement(0, kxx=stfx, kyy=stfy, cxx=0, n_link=7)
bearing1 = rs.BearingElement(6, kxx=stfx, kyy=stfy, cxx=0)
bearing2 = rs.BearingElement(7, kxx=stfx, kyy=stfy, cxx=0)

bearings = [bearing0, bearing1, bearing2]

# Modelando o centro de massa
pm0 = rs.PointMass(n=7, m=0.3)

pointmass = [pm0]

# Modelando o rotor (eixo + discos + mancais + massa pontual)
rotor1 = rs.Rotor(shaft_elem, disks, bearings, pointmass)

# Gerando o Diagrama de Campbell
samples = 30
speed_range = np.linspace(300, 3000, samples)  # Velocidade variando de 300 a 3000 RPM

campbell = rotor1.run_campbell(speed_range)

plot_campbell = campbell.plot(frequency_units="RPM", harmonics=[0.5, 1, 2])
