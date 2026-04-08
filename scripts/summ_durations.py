import pandas as pd
import ast

df = pd.read_csv('res_fleur_05_12_2.csv')

symbols_col = 'symbols'

if symbols_col not in df.columns:
    print("Column 'symbols' not found!")
    exit(1)

chemical_symbols = []
for symbols_str in df[symbols_col]:
    try:
        symbols_list = ast.literal_eval(symbols_str)
        # take first unique str (main type)
        unique_symbols = list(set(symbols_list))
        chemical_symbols.append(unique_symbols[0] if unique_symbols else None)
    except:
        chemical_symbols.append(None)

duration_by_structure = {}

# group by chemical str and sum duration
for symbol, duration in zip(chemical_symbols, df['duration']):
    if pd.isna(duration) or symbol is None:
        continue
    
    if symbol not in duration_by_structure:
        duration_by_structure[symbol] = 0
    
    duration_by_structure[symbol] += float(duration)

print("=" * 50)
print("TOTAL COMPUTATION TIME")
print("=" * 50)

total_all = sum(duration_by_structure.values())
for structure, total_duration in sorted(duration_by_structure.items()):
    print(f"{structure:>3} | {total_duration:>10.2f} h")

print("-" * 50)
print(f"TOTAL  | {total_all:>10.2f} h")
print("=" * 50)

print("\nLONGEST COMPUTATIONS:")
sorted_structures = sorted(duration_by_structure.items(), key=lambda x: x[1], reverse=True)[:10]
for i, (structure, duration) in enumerate(sorted_structures, 1):
    print(f"{i:>2}. {structure:>3} | {duration:>10.2f} h")

print("\nSTATISTICS:")
print(f"Number of structures: {len(duration_by_structure)}")
print(f"Total time: {total_all:.2f} hours")
print(f"Average time per structure: {total_all/len(duration_by_structure):.2f} h")
print(f"Max time: {max(duration_by_structure.values()):.2f} h")