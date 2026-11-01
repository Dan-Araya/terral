"""Compatibilidad local mínima para pandas.to_markdown; no es el paquete tabulate.

Solo admite tablas Markdown pipe y DataFrames, usados por este estudio.
La versión declara compatibilidad de interfaz para la comprobación de pandas.
"""
__version__='0.9.0'
def tabulate(tabular_data,headers='keys',showindex=False,floatfmt='g',tablefmt='pipe',**kwargs):
 import math,numbers
 if tablefmt!='pipe': raise ValueError('Solo salida Markdown pipe')
 if not hasattr(tabular_data,'itertuples'): raise TypeError('Solo DataFrame')
 df=tabular_data; names=list(df.columns) if headers=='keys' else list(headers)
 if showindex: names=['indice']+names
 def fmt(value):
  if value is None:return ''
  if isinstance(value,numbers.Real):
   if math.isnan(value):return '—'
   if isinstance(value,numbers.Integral):return str(value)
   return format(value,floatfmt)
  return str(value).replace('|','\\|').replace('\n',' ')
 rows=[]
 for idx,values in zip(df.index,df.itertuples(index=False,name=None)):
  cells=([idx] if showindex else [])+list(values);rows.append('| '+' | '.join(map(fmt,cells))+' |')
 return '\n'.join(['| '+' | '.join(map(str,names))+' |','| '+' | '.join('---' for _ in names)+' |']+rows)
