import math
from app.utils.geofence import (GeofenceError, haversine_m, validar_coordenadas, validar_proximidade)

POSTO = (-7.11490750, -34.86109731)  # posto id 1 do banco real

def erro(fn, *a, **k):
    try:
        fn(*a, **k)
    except GeofenceError as e:
        return e
    raise AssertionError("não levantou GeofenceError")

# haversine
assert haversine_m(*POSTO, *POSTO) == 0
d = haversine_m(0.0, 10.0, 1.0, 10.0)
assert 110_500 < d < 111_800, d                       # ~111,2 km por grau de latitude
assert abs(haversine_m(*POSTO, -7.12, -34.87) - haversine_m(-7.12, -34.87, *POSTO)) < 1e-6
# posto 1 -> posto 2 do banco real (Bezerra e Lucena -> Shell Freeway), ~1,3 km
d12 = haversine_m(-7.11490750, -34.86109731, -7.11932697, -34.84227595)
assert 1_900 < d12 < 2_300, d12

# validação de coordenadas
for ruim in [(None, 1), (1, None), ("abc", 1), (float("nan"), 1), (float("inf"), 1),
             (91, 0), (0, 181), (True, False), (0, 0), ("", ""), ([], {})]:
    e = erro(validar_coordenadas, *ruim)
    assert e.codigo in ("GPS_AUSENTE", "GPS_INVALIDO"), (ruim, e.codigo)
assert erro(validar_coordenadas, None, None).codigo == "GPS_AUSENTE"
assert validar_coordenadas("-7.1149", "-34.8610") == (-7.1149, -34.8610)   # string numérica aceita

# dentro do raio
r = validar_proximidade(-7.1150, -34.8611, 10, *POSTO)
assert r.distancia_m < 50 and r.raio_efetivo_m == 510

# 1 grau de latitude longe -> fora do raio, código estável e status 403
e = erro(validar_proximidade, -6.1149, -34.8611, 10, *POSTO)
assert (e.codigo, e.status) == ("FORA_DO_RAIO", 403) and e.extra["distancia_m"] > 100_000
corpo, status = e.para_resposta()
assert status == 403 and corpo["codigo"] == "FORA_DO_RAIO" and "error" in corpo

# 20 km (o bug antigo) agora é rejeitado
e = erro(validar_proximidade, -7.11490750 + 0.18, -34.86109731, 5, *POSTO)   # ~20 km
assert e.codigo == "FORA_DO_RAIO"

# precisão: folga concedida, limitada, e fix impreciso rejeitado
lat_550 = -7.11490750 + 550 / 111_195.0        # ~550 m ao norte
assert erro(validar_proximidade, lat_550, -34.86109731, None, *POSTO).codigo == "FORA_DO_RAIO"   # sem precisão: estrito
assert validar_proximidade(lat_550, -34.86109731, 60, *POSTO)                                   # 500 + 60 > 550
e = erro(validar_proximidade, lat_550, -34.86109731, 151, *POSTO)
assert (e.codigo, e.status) == ("GPS_IMPRECISO", 422)
r = validar_proximidade(-7.1150, -34.8611, 149, *POSTO)
assert r.raio_efetivo_m == 600                   # folga limitada a 100 m

# precisão inválida é ignorada (tratada como desconhecida), não derruba
assert validar_proximidade(-7.1150, -34.8611, "xyz", *POSTO).raio_efetivo_m == 500
assert validar_proximidade(-7.1150, -34.8611, -5, *POSTO).raio_efetivo_m == 500

# raio customizado
assert erro(validar_proximidade, lat_550, -34.86109731, None, *POSTO, raio_m=200).codigo == "FORA_DO_RAIO"

# posto sem coordenadas -> erro de dados, 500
assert erro(validar_proximidade, -7.1150, -34.8611, 5, None, None).codigo == "POSTO_SEM_COORDENADAS"
print("geofence: todos os testes passaram")