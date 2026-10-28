from sqw.em import epr_kerr
from sqw.io import write_json

# One ideal junction, unit inductive participation: alpha=-f^2/(8 EJ)=-250 MHz.
single = epr_kerr([5.0],[12.5],[[1.0]])
print('Single-mode limit (MHz):',single['anharmonicity_MHz'])
# Independent illustrative participations, NOT values extracted from the demo geometry.
two = epr_kerr([5.0,7.2],[14.5],[[.95],[.03]])
write_json('build/modules/06/epr_example.json',{'synthetic':True,**two})
