import math
from functools import reduce
from ase.atoms import Atoms


FORMULA_SEQUENCE = [
    "Fr",
    "Cs",
    "Rb",
    "K",
    "Na",
    "Li",
    "Be",
    "Mg",
    "Ca",
    "Sr",
    "Ba",
    "Ra",
    "Sc",
    "Y",
    "La",
    "Ce",
    "Pr",
    "Nd",
    "Pm",
    "Sm",
    "Eu",
    "Gd",
    "Tb",
    "Dy",
    "Ho",
    "Er",
    "Tm",
    "Yb",
    "Ac",
    "Th",
    "Pa",
    "U",
    "Np",
    "Pu",
    "Ti",
    "Zr",
    "Hf",
    "V",
    "Nb",
    "Ta",
    "Cr",
    "Mo",
    "W",
    "Fe",
    "Ru",
    "Os",
    "Co",
    "Rh",
    "Ir",
    "Mn",
    "Tc",
    "Re",
    "Ni",
    "Pd",
    "Pt",
    "Cu",
    "Ag",
    "Au",
    "Zn",
    "Cd",
    "Hg",
    "B",
    "Al",
    "Ga",
    "In",
    "Tl",
    "Pb",
    "Sn",
    "Ge",
    "Si",
    "C",
    "N",
    "P",
    "As",
    "Sb",
    "Bi",
    "H",
    "Po",
    "Te",
    "Se",
    "S",
    "O",
    "At",
    "I",
    "Br",
    "Cl",
    "F",
    "He",
    "Ne",
    "Ar",
    "Kr",
    "Xe",
    "Rn",
]


def get_formula_dict(ase_obj: Atoms, find_gcd=True):
    parsed_formula: dict[str, int] = {}
    symbols: list[str] = ase_obj.get_chemical_symbols()

    for label in symbols:
        if label not in parsed_formula:
            parsed_formula[label] = 1
        else:
            parsed_formula[label] += 1

    expanded = reduce(math.gcd, parsed_formula.values()) if find_gcd else 1
    if expanded > 1:
        parsed_formula = {
            el: int(content / float(expanded)) for el, content in parsed_formula.items()
        }
    return parsed_formula


def get_formula(ase_obj, find_gcd=True):
    parsed_formula = get_formula_dict(ase_obj, find_gcd)

    atoms = parsed_formula.keys()
    atoms = [x for x in FORMULA_SEQUENCE if x in atoms] + [
        x for x in atoms if x not in FORMULA_SEQUENCE
    ]
    formula = ""
    for atom in atoms:
        index = parsed_formula[atom]
        index = "" if index == 1 else str(index)
        formula += atom + index

    return formula