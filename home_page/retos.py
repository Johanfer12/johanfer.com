"""Datos de la página de Retos (/retos/).

Cada tema se elige con ?tema= desde el botón flotante y se ve solo, sin
agruparlos. De momento solo Clima tiene contenido; Economía e IA salen como
«próximamente».
"""

TEMAS = (
    ('clima', 'Cambio climático'),
    ('economia', 'Economía'),
    ('ia', 'Inteligencia artificial'),
)
TEMA_POR_DEFECTO = 'clima'

# Límites planetarios según el Planetary Health Check 2025 (PIK, 24/09/2025):
# siete de nueve superados; la acidificación oceánica es la que se sumó este año.
# `superado` es el veredicto del informe, no una medida propia.
LIMITES_PLANETARIOS = (
    {'nombre': 'Cambio climático', 'superado': True,
     'descripcion': 'El CO₂ del aire ya supera las 420 ppm (partes por millón: de cada millón de moléculas de aire, más de 420 son de CO₂), cuando el límite seguro es 350 ppm. Antes de la industrialización eran unas 280.\n\nMás CO₂ atrapa más calor: olas de calor más intensas, deshielo de glaciares y polos, subida del nivel del mar, sequías e incendios más fuertes y cosechas en riesgo.'},
    {'nombre': 'Integridad de la biosfera', 'superado': True,
     'descripcion': 'La biosfera es el conjunto de seres vivos del planeta y de los ecosistemas que forman. Hoy las especies se extinguen a un ritmo muy superior al natural, y en muchos lugares queda menos naturaleza intacta.\n\nCada pérdida debilita cosas de las que dependemos sin notarlo: la polinización de los cultivos, la fertilidad del suelo, el agua limpia y la capacidad de los ecosistemas para aguantar crisis como sequías o plagas.'},
    {'nombre': 'Cambio en el uso del suelo', 'superado': True,
     'descripcion': 'Este límite mide cuánto bosque original queda: cerca del 60 %, cuando el mínimo seguro es 75 %. Se talan bosques para cultivar, criar ganado y construir.\n\nLos bosques absorben carbono, ayudan a generar lluvia, enfrían el aire y son el hogar de la mayoría de las especies terrestres. Sin ellos hay más calor, menos lluvia y más especies en peligro.'},
    {'nombre': 'Agua dulce', 'superado': True,
     'descripcion': 'Mide cuánto hemos alterado el agua dulce: la de ríos, lagos y acuíferos (llamada «agua azul») y también la humedad del suelo y de las plantas («agua verde»). Se ha modificado con presas, riego, deforestación y cambio climático.\n\nEl resultado son sequías e inundaciones más bruscas, ríos que ya no llegan al mar, cultivos con menos agua y humedales en retroceso.'},
    {'nombre': 'Ciclos del nitrógeno y el fósforo', 'superado': True,
     'descripcion': 'El nitrógeno y el fósforo son los nutrientes de los fertilizantes. Se usan en tanta cantidad que las plantas no los absorben todos, y el sobrante se va a ríos, lagos y mares.\n\nAllí hacen crecer algas en exceso que, al descomponerse, gastan el oxígeno del agua y crean «zonas muertas» donde los peces no pueden vivir. También contaminan el agua potable.'},
    {'nombre': 'Nuevas entidades (plásticos, químicos)', 'superado': True,
     'descripcion': 'Son sustancias y materiales que la naturaleza no conocía: plásticos, pesticidas, químicos industriales, residuos radiactivos, organismos modificados. Se crean más rápido de lo que se evalúa su efecto.\n\nMuchas no se degradan y se acumulan en el agua, el suelo e incluso en nuestro cuerpo (los microplásticos). El riesgo es que sus efectos se descubran cuando ya es casi imposible retirarlas.'},
    {'nombre': 'Acidificación de los océanos', 'superado': True, 'nuevo': True,
     'descripcion': 'El océano absorbe cerca de una cuarta parte del CO₂ que emitimos y, al disolverse, el agua se vuelve más ácida. Desde la era industrial su acidez ha subido entre un 30 y un 40 %.\n\nEl agua más ácida dificulta que corales, ostras, mejillones y plancton formen su concha o esqueleto. Como ese plancton es la base de la cadena alimentaria marina, el daño llega a los peces y a las personas que viven de la pesca.'},
    {'nombre': 'Carga de aerosoles', 'superado': False,
     'descripcion': 'Los aerosoles son partículas diminutas suspendidas en el aire: polvo, hollín, humo y contaminación de fábricas y vehículos. Alteran cuánta luz solar llega al suelo y cómo se forman las nubes y la lluvia.\n\nA escala global este límite aún no se ha pasado, pero en algunas regiones, como el sur de Asia, ya hay daño: cambios en los monzones (la lluvia de la que depende la comida de millones de personas) y un aire que enferma.'},
    {'nombre': 'Capa de ozono', 'superado': False,
     'descripcion': 'La capa de ozono es un escudo en la atmósfera alta que frena la radiación ultravioleta, la que causa quemaduras, cáncer de piel y daño a los cultivos. Productos como los viejos aerosoles y refrigerantes la estaban destruyendo.\n\nSe está recuperando gracias al Protocolo de Montreal (1987), un acuerdo mundial que prohibió esas sustancias. Es la prueba de que, cuando los países actúan juntos, el daño se puede revertir.'},
)

# Texto del modal de la «i» de cada gráfica (párrafos separados por línea en blanco).
INFO_GRAFICAS = {
    'limites': 'Los científicos han definido nueve «límites planetarios»: los procesos que mantienen estable la Tierra, como el clima, el agua o la biodiversidad. Para cada uno hay una zona segura, la de las condiciones estables en las que la humanidad ha prosperado durante unos 10.000 años.\n\nPasar un límite no es un precipicio inmediato, pero aumenta el riesgo de cambios bruscos e irreversibles. Y como los sistemas están conectados, que se deteriore uno empuja a los demás. En 2023 eran seis los superados; en 2025, siete.\n\nPulsa el «?» de cada límite para ver qué significa.',
    'nino': 'El Niño es un calentamiento anormal de una franja del océano Pacífico tropical que se repite cada dos a siete años. «Niño 3.4» es el nombre de la zona concreta que los científicos miden: una región del Pacífico central, cerca del ecuador. Si su agua está más de 0,5 °C por encima de lo normal durante varios meses, se declara El Niño.\n\nLa gráfica muestra esa «anomalía»: cuántos grados por encima (o por debajo) de lo normal está el agua cada mes. 1997 y 2015 fueron los dos El Niño más fuertes de la era moderna; 2026 los está superando.\n\nImporta porque cambia las lluvias y las temperaturas de medio mundo: sequías en unos lugares e inundaciones en otros, con cosechas y pesca afectadas. En Colombia suele significar menos lluvia y más calor. Y como se suma al calentamiento global, los años con un El Niño fuerte suelen traer récords de temperatura, sobre todo unos meses después del pico.',
    'aire':
        'La temperatura del aire cerca de la superficie, promediada sobre todo el planeta (tierra y mar), es el termómetro más conocido del calentamiento global. La gráfica muestra cuántos grados más cálido fue cada año que el promedio de 1850-1900, es decir, antes de que quemar carbón, petróleo y gas cambiara el clima.\n\n'
        'En 2015, el Acuerdo de París fijó el objetivo de no pasar de 1,5 °C. Puede parecer poco, pero es un promedio de todo el planeta: cada décima de más significa olas de calor más frecuentes, más sequías, tormentas más fuertes y más hielo perdido.\n\n'
        'Ojo con las cifras: cada institución calcula esta temperatura de forma algo distinta. Con la serie de NOAA, que usa esta gráfica, 2024 (el año más cálido) quedó en +1,42 °C; otras, como Copernicus y la OMM, lo sitúan por encima de 1,5 °C. Lo que todas coinciden en mostrar es la tendencia. El punto de 2026 es solo de enero a agosto, y el Niño tarda unos meses en reflejarse en el aire: lo más fuerte se espera en 2027.',
    'nivel':
        'El nivel medio del mar sube por dos razones: el agua se dilata al calentarse, y se derrite hielo de glaciares, de Groenlandia y de la Antártida que termina en el océano. Desde 1993 se mide con satélites, con un error de milímetros.\n\n'
        'La gráfica muestra cuántos centímetros ha subido el mar respecto a 1993, en promedio de todo el planeta. Parece poco (unos 11 cm), pero el ritmo se acelera, y cada centímetro cuenta: las tormentas y las mareas altas se montan sobre un mar más alto, así que las inundaciones costeras son más frecuentes y dañinas, y el agua salada se mete en acuíferos y cultivos.\n\n'
        'La línea punteada no es un pronóstico oficial: prolonga hasta 2030 la tendencia que muestran los datos, con su aceleración incluida. Sirve para ver hacia dónde apunta la curva si nada cambia.',
    'mar': 'La gráfica muestra la «anomalía» de la temperatura de los océanos: cuántos grados más cálidos están que el promedio del siglo XX (1901-2000). Cada línea es un año, mes a mes.\n\nImporta porque los océanos absorben más del 90 % del calor extra que atrapan los gases de efecto invernadero: son el gran amortiguador del planeta. Un mar más caliente alimenta huracanes más intensos, blanquea y mata corales, hace subir el nivel del mar (el agua caliente se dilata) y devuelve más calor al aire. Además tarda mucho en enfriarse: lo que se calienta hoy se queda.',
    'co2': 'El CO₂ (dióxido de carbono) es el principal gas que calienta el planeta. Se mide en «ppm», partes por millón: 427 ppm significa que de cada millón de moléculas de aire, 427 son de CO₂. Parece muy poco, pero basta para cambiar el clima.\n\nLa curva viene del observatorio de Mauna Loa (Hawái), que mide el aire desde 1958, lejos de ciudades e industrias. Muestra que el CO₂ sube cada año sin pausa: de unas 280 ppm antes de la industria a más de 427 hoy. El límite de 350 ppm se cruzó a finales de los años 80.\n\nImporta porque el CO₂ permanece siglos en la atmósfera: lo que emitimos hoy lo seguirán sintiendo las próximas generaciones.'}

# Anomalía mensual de la temperatura del mar en la región Niño 3.4 (°C), de
# enero a diciembre. Fuente: NOAA CPC, `sstoi.indices` (OISST), leído el
# 30/09/2026. 2026 llega hasta agosto; 1997 y 2015 son los dos «super El Niño»
# con los que se compara.
NINO34_MENSUAL = {
    '1997': [-0.61, -0.39, -0.36, -0.11, 0.40, 0.81, 1.27, 1.68, 1.84, 1.96, 2.11, 2.10],
    '2015': [0.51, 0.75, 0.44, 0.82, 0.83, 1.02, 1.26, 1.65, 1.79, 2.21, 2.72, 2.39],
    '2026': [-0.54, -0.20, 0.03, 0.47, 0.94, 1.55, 2.03, 2.52],
}
# Último dato semanal (NOAA CPC, `wksst9120.for`): semana del 23/09/2026.
NINO34_SEMANAL_ULTIMO = 3.1


# Anomalía mensual de la temperatura media de los océanos (°C) sobre el promedio
# 1901-2000, enero a diciembre. Fuente: NOAA NCEI, Climate at a Glance, océano
# global (serie desde 1850), leído el 30/09/2026. 2026 llega hasta agosto.
TEMP_MAR_MENSUAL = {
    '2023': [0.67, 0.69, 0.81, 0.87, 0.85, 0.93, 0.99, 1.02, 1.02, 1.0, 0.98, 0.98],
    '2024': [1.03, 1.03, 0.97, 1.0, 0.96, 0.95, 0.95, 0.95, 0.93, 0.92, 0.89, 0.84],
    '2025': [0.88, 0.86, 0.88, 0.84, 0.84, 0.83, 0.88, 0.87, 0.85, 0.79, 0.74, 0.77],
    '2026': [0.82, 0.87, 0.9, 0.95, 0.94, 0.99, 1.02, 1.08],
}
# Récord mensual anterior a agosto de 2026 en toda la serie (enero y febrero de 2024).
TEMP_MAR_RECORD_PREVIO = 1.03

# CO₂ atmosférico, media anual en Mauna Loa (ppm). Fuente: NOAA GML, leído el
# 30/09/2026. Referencias: ~280 ppm antes de la industrialización y 350 ppm como
# límite seguro del marco de límites planetarios.
CO2_ANUAL = {
    1959: 315.98,
    1960: 316.91,
    1961: 317.64,
    1962: 318.45,
    1963: 318.99,
    1964: 319.62,
    1965: 320.04,
    1966: 321.37,
    1967: 322.18,
    1968: 323.05,
    1969: 324.62,
    1970: 325.68,
    1971: 326.32,
    1972: 327.46,
    1973: 329.68,
    1974: 330.19,
    1975: 331.13,
    1976: 332.03,
    1977: 333.84,
    1978: 335.41,
    1979: 336.84,
    1980: 338.76,
    1981: 340.12,
    1982: 341.48,
    1983: 343.15,
    1984: 344.87,
    1985: 346.35,
    1986: 347.61,
    1987: 349.31,
    1988: 351.69,
    1989: 353.2,
    1990: 354.45,
    1991: 355.7,
    1992: 356.54,
    1993: 357.21,
    1994: 358.96,
    1995: 360.97,
    1996: 362.74,
    1997: 363.88,
    1998: 366.84,
    1999: 368.54,
    2000: 369.71,
    2001: 371.32,
    2002: 373.45,
    2003: 375.98,
    2004: 377.7,
    2005: 379.98,
    2006: 382.09,
    2007: 384.02,
    2008: 385.83,
    2009: 387.64,
    2010: 390.1,
    2011: 391.85,
    2012: 394.06,
    2013: 396.74,
    2014: 398.81,
    2015: 401.01,
    2016: 404.41,
    2017: 406.76,
    2018: 408.72,
    2019: 411.65,
    2020: 414.21,
    2021: 416.41,
    2022: 418.53,
    2023: 421.08,
    2024: 424.61,
    2025: 427.35,
}
CO2_PREINDUSTRIAL = 280
CO2_LIMITE_SEGURO = 350
# Mauna Loa, media mensual de agosto de 2026 y máximo estacional (mayo de 2026).
CO2_AGOSTO_2026 = 427.55
CO2_MAXIMO_2026 = 432.34


# Temperatura del aire: anomalía anual de la superficie global (tierra y mar),
# en °C sobre el promedio 1901-2000. Fuente: NOAA NCEI, Climate at a Glance,
# leído el 30/09/2026. Al mostrarla se traslada a la referencia 1850-1900
# (preindustrial) restando AIRE_PREINDUSTRIAL, que es la media de 1850-1900 de
# esta misma serie; otras instituciones (Copernicus, OMM) usan otra
# reconstrucción del periodo preindustrial y dan cifras algo distintas.
AIRE_PREINDUSTRIAL = -0.1690
AIRE_OBJETIVO_PARIS = 1.5
AIRE_ANUAL_NOAA = {
    1880: -0.19,
    1881: -0.10,
    1882: -0.18,
    1883: -0.18,
    1884: -0.28,
    1885: -0.23,
    1886: -0.27,
    1887: -0.35,
    1888: -0.13,
    1889: -0.06,
    1890: -0.32,
    1891: -0.24,
    1892: -0.32,
    1893: -0.33,
    1894: -0.33,
    1895: -0.23,
    1896: -0.13,
    1897: -0.12,
    1898: -0.26,
    1899: -0.16,
    1900: -0.08,
    1901: -0.12,
    1902: -0.22,
    1903: -0.33,
    1904: -0.39,
    1905: -0.27,
    1906: -0.18,
    1907: -0.35,
    1908: -0.39,
    1909: -0.38,
    1910: -0.35,
    1911: -0.37,
    1912: -0.30,
    1913: -0.28,
    1914: -0.12,
    1915: -0.07,
    1916: -0.29,
    1917: -0.42,
    1918: -0.33,
    1919: -0.20,
    1920: -0.18,
    1921: -0.15,
    1922: -0.23,
    1923: -0.22,
    1924: -0.21,
    1925: -0.19,
    1926: -0.07,
    1927: -0.17,
    1928: -0.15,
    1929: -0.30,
    1930: -0.10,
    1931: -0.05,
    1932: -0.11,
    1933: -0.24,
    1934: -0.10,
    1935: -0.13,
    1936: -0.09,
    1937: -0.00,
    1938: 0.01,
    1939: 0.02,
    1940: 0.16,
    1941: 0.21,
    1942: 0.08,
    1943: 0.09,
    1944: 0.21,
    1945: 0.13,
    1946: -0.00,
    1947: -0.00,
    1948: -0.04,
    1949: -0.04,
    1950: -0.13,
    1951: -0.02,
    1952: 0.04,
    1953: 0.10,
    1954: -0.08,
    1955: -0.13,
    1956: -0.17,
    1957: 0.06,
    1958: 0.09,
    1959: 0.08,
    1960: -0.01,
    1961: 0.08,
    1962: 0.04,
    1963: 0.06,
    1964: -0.18,
    1965: -0.08,
    1966: -0.04,
    1967: -0.01,
    1968: -0.05,
    1969: 0.09,
    1970: 0.04,
    1971: -0.08,
    1972: 0.05,
    1973: 0.17,
    1974: -0.05,
    1975: -0.01,
    1976: -0.06,
    1977: 0.20,
    1978: 0.11,
    1979: 0.19,
    1980: 0.29,
    1981: 0.33,
    1982: 0.15,
    1983: 0.32,
    1984: 0.17,
    1985: 0.14,
    1986: 0.22,
    1987: 0.33,
    1988: 0.38,
    1989: 0.26,
    1990: 0.42,
    1991: 0.40,
    1992: 0.23,
    1993: 0.26,
    1994: 0.32,
    1995: 0.46,
    1996: 0.34,
    1997: 0.48,
    1998: 0.61,
    1999: 0.40,
    2000: 0.40,
    2001: 0.53,
    2002: 0.59,
    2003: 0.60,
    2004: 0.53,
    2005: 0.66,
    2006: 0.63,
    2007: 0.62,
    2008: 0.52,
    2009: 0.65,
    2010: 0.71,
    2011: 0.60,
    2012: 0.63,
    2013: 0.66,
    2014: 0.73,
    2015: 0.88,
    2016: 1.00,
    2017: 0.93,
    2018: 0.86,
    2019: 0.99,
    2020: 1.01,
    2021: 0.86,
    2022: 0.89,
    2023: 1.17,
    2024: 1.25,
    2025: 1.12,
}
# Media de enero a agosto (mismo formato), para comparar el arranque de 2026
# con los de 2024 y 2025. El año completo de 2026 aún no existe.
AIRE_ENE_AGO_NOAA = {2024: 1.25, 2025: 1.13, 2026: 1.16}

# Nivel medio global del mar (cm sobre la media de 1993), media anual. Fuente:
# CU Sea Level Research Group, altimetría por satélite, versión 2026_rel1 (datos
# hasta febrero de 2026; con la estacionalidad y el ajuste isostático glaciar
# quitados), leído el 30/09/2026. Solo años completos.
NIVEL_MAR_CM = {
    1993: 0.0,
    1994: 0.5,
    1995: 1.0,
    1996: 1.3,
    1997: 1.8,
    1998: 1.7,
    1999: 1.6,
    2000: 2.1,
    2001: 2.7,
    2002: 2.8,
    2003: 3.0,
    2004: 3.3,
    2005: 3.8,
    2006: 3.9,
    2007: 3.9,
    2008: 4.3,
    2009: 4.7,
    2010: 4.8,
    2011: 4.8,
    2012: 5.8,
    2013: 6.1,
    2014: 6.5,
    2015: 7.4,
    2016: 7.7,
    2017: 7.8,
    2018: 8.1,
    2019: 8.8,
    2020: 9.0,
    2021: 9.5,
    2022: 9.7,
    2023: 10.4,
    2024: 10.8,
    2025: 10.8,
}
# Línea punteada hasta 2030: ajuste cuadrático (con aceleración) a las medias
# anuales 1993-2025, desplazado para que arranque en el último dato real. Es una
# extrapolación de la tendencia observada, NO un pronóstico oficial.
NIVEL_MAR_PROYECCION_HASTA = 2030


def _coma(valor, decimales):
    """Número con coma decimal; el sitio corre con LANGUAGE_CODE en inglés, que pondría punto."""
    return f'{valor:.{decimales}f}'.replace('.', ',')


def comparacion_nino34():
    """2026 frente a los dos El Niño más fuertes antes de él, en el último mes con dato y en el pico.

    Devuelve las cifras ya con coma decimal, listas para el texto.
    """
    mes = len(NINO34_MENSUAL['2026'])  # último mes con dato (agosto)
    ahora = NINO34_MENSUAL['2026'][-1]
    mismo_mes = {y: NINO34_MENSUAL[y][mes - 1] for y in ('1997', '2015')}
    return {
        'ahora': _coma(ahora, 2),
        'mismo_mes': {y: _coma(v, 2) for y, v in mismo_mes.items()},
        'pico': {y: _coma(max(NINO34_MENSUAL[y]), 2) for y in ('1997', '2015')},
        'diferencia': _coma(ahora - max(mismo_mes.values()), 1),
        'semanal': _coma(NINO34_SEMANAL_ULTIMO, 1),
    }


def resumen_mar_y_co2():
    """Cifras de las dos gráficas nuevas, con coma decimal."""
    ahora = TEMP_MAR_MENSUAL['2026'][-1]
    ultimo_anio = max(CO2_ANUAL)
    return {
        'mar_ahora': _coma(ahora, 2),
        'mar_record_previo': _coma(TEMP_MAR_RECORD_PREVIO, 2),
        'mar_es_record': ahora > TEMP_MAR_RECORD_PREVIO,
        'co2_anio': ultimo_anio,
        'co2_anual': _coma(CO2_ANUAL[ultimo_anio], 1),
        'co2_maximo': _coma(CO2_MAXIMO_2026, 1),
        'co2_sobre_limite': _coma(CO2_ANUAL[ultimo_anio] - CO2_LIMITE_SEGURO, 0),
    }


def _en_preindustrial(valor_noaa):
    return valor_noaa - AIRE_PREINDUSTRIAL


def aire_para_grafica():
    """Serie anual sobre 1850-1900 y el punto de enero-agosto de 2026."""
    anios = list(AIRE_ANUAL_NOAA)
    return {
        'anios': anios + [2026],
        'valores': [round(_en_preindustrial(v), 2) for v in AIRE_ANUAL_NOAA.values()],
        'ene_ago_2026': round(_en_preindustrial(AIRE_ENE_AGO_NOAA[2026]), 2),
        'objetivo': AIRE_OBJETIVO_PARIS,
    }


def nivel_mar_para_grafica():
    """Medias anuales medidas y la prolongación de la tendencia hasta 2030.

    La prolongación es un ajuste cuadrático por mínimos cuadrados, así que
    recoge la aceleración; se desplaza para empezar en el último dato medido.
    """
    import numpy as np  # solo la usa esta vista: no se paga al importar el módulo

    anios = np.array(list(NIVEL_MAR_CM), dtype=float)
    valores = np.array(list(NIVEL_MAR_CM.values()))
    coef = np.polyfit(anios - 2010, valores, 2)
    ajuste = lambda y: float(np.polyval(coef, y - 2010))
    ultimo = int(anios[-1])
    proyeccion = {y: round(NIVEL_MAR_CM[ultimo] + ajuste(y) - ajuste(ultimo), 1)
                  for y in range(ultimo + 1, NIVEL_MAR_PROYECCION_HASTA + 1)}
    return {
        'anios': list(range(int(anios[0]), NIVEL_MAR_PROYECCION_HASTA + 1)),
        'medido': list(NIVEL_MAR_CM.values()),
        'proyeccion': [None] * (len(NIVEL_MAR_CM) - 1) + [NIVEL_MAR_CM[ultimo]] + list(proyeccion.values()),
        'proyeccion_final': proyeccion[NIVEL_MAR_PROYECCION_HASTA],
    }


def _pendiente_mm_anio(desde, hasta):
    import numpy as np

    anios = np.arange(desde, hasta + 1, dtype=float)
    valores = np.array([NIVEL_MAR_CM[int(a)] for a in anios])
    return float(np.polyfit(anios, valores, 1)[0]) * 10


def resumen_aire_y_nivel():
    """Cifras de los textos de las dos gráficas, con coma decimal."""
    ene_ago = {y: _en_preindustrial(v) for y, v in AIRE_ENE_AGO_NOAA.items()}
    mas_calido = max(AIRE_ANUAL_NOAA, key=AIRE_ANUAL_NOAA.get)
    ultimo = max(NIVEL_MAR_CM)
    return {
        'aire_anio_record': mas_calido,
        'aire_valor_record': _coma(_en_preindustrial(AIRE_ANUAL_NOAA[mas_calido]), 2),
        'aire_2026': _coma(ene_ago[2026], 2),
        'aire_2024_ene_ago': _coma(ene_ago[2024], 2),
        'aire_2025_ene_ago': _coma(ene_ago[2025], 2),
        # Segundo arranque de año más cálido si solo 2024 lo supera.
        'aire_2026_segundo': sorted(AIRE_ENE_AGO_NOAA.values(), reverse=True)[1] == AIRE_ENE_AGO_NOAA[2026],
        'nivel_anio': ultimo,
        'nivel_cm': _coma(NIVEL_MAR_CM[ultimo], 1),
        'nivel_ritmo_inicio': _coma(_pendiente_mm_anio(1993, 2002), 1),
        'nivel_ritmo_actual': _coma(_pendiente_mm_anio(ultimo - 9, ultimo), 1),
        'nivel_2030': _coma(nivel_mar_para_grafica()['proyeccion_final'], 1),
    }
