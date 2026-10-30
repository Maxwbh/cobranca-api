---
title: Cobranca-API — en español
description: Cobrar en Brasil desde Paraguay, Argentina o Uruguay — boleto bancario, Pix y CNAB por API REST. Guía en español, con glosario de todos los campos del boleto.
lang: es
---

# Cobrar en Brasil con boleto bancario y Pix, por API REST

**Para empresas del Mercosur — Ciudad del Este, Encarnación, Pedro Juan,
Posadas, Rivera — que venden a clientes brasileños y necesitan cobrar en
reales.** La Cobranca-API emite boleto bancario, genera Pix y produce los
archivos CNAB que los bancos brasileños exigen, todo por HTTP, desde cualquier
lenguaje: PHP, Java, C#, Node, Go, Delphi, Oracle APEX, PL/SQL o Python.

Es software libre (MIT), **100% Python, un solo container**, y se instala en su
propio servidor: no hay instancia pública ni intermediario cobrando comisión
por venta.

> Esta página es la puerta de entrada en español. La referencia técnica
> completa — campos, rutas, códigos de error — está en portugués, en el
> [Swagger](../swagger/) y en la [documentación](../). El glosario de abajo
> traduce el vocabulario que va a encontrar ahí.

---

## Lo que necesita antes de empezar

La API habla con el **sistema bancario brasileño**. Eso impone tres
condiciones que ningún software resuelve por usted:

| Necesita | Por qué |
|---|---|
| **Una empresa con CNPJ** (o una persona con CPF) en Brasil | El boleto y el Pix se emiten a nombre de un contribuyente brasileño. Es el campo `documento_cedente`, y es obligatorio. |
| **Una cuenta en un banco brasileño** | La plata entra ahí. Para boleto, el banco tiene que habilitar *cobrança* y darle un **convenio** y una **cartera**. |
| **El documento brasileño del cliente** | El pagador se identifica por CPF (persona) o CNPJ (empresa). Es `sacado_documento`, también obligatorio. |

Cédula, RUC o CUIT no sirven en ninguno de los dos campos de documento. Si
manda uno, la API responde `400` con el campo y el motivo:
`sacado_documento: CPF/CNPJ brasileiro inválido`.

Si su empresa todavía no tiene CNPJ, cuenta o convenio en Brasil, **la
apertura — empresa, cuenta y convenio de cobranza — es un trámite, no un
problema de software**, y
[M&S do Brasil](https://msbrasil.inf.br) lo acompaña como servicio, junto con
la integración. La API no cambia esa barrera; la deja explícita.

---

## Dos caminos, un solo contrato

**Offline — boleto en PDF, CNAB y carnet.** La API genera el boleto con el
código de barras calculado localmente, según el layout FEBRABAN de cada banco
(**19 bancos offline**), y produce el archivo de **remesa** CNAB 240/400 que
usted sube al portal del banco para registrar los títulos. El **retorno** CNAB
que el banco devuelve se sube a la API y ella le dice qué se pagó. No hace
falta credencial de API del banco: solo el convenio.

**Online — Pix, boleto registrado y Pix Automático.** La API habla
directamente con la API del banco (OAuth2 + certificado mTLS). Hoy, **4 bancos
online**: C6, Sicoob, Inter e Itaú. El boleto se registra al instante, el Pix
genera un QR dinámico vinculado al título (**Bolepix**), y la liquidación llega
por webhook.

Es el mismo `POST /cobranca`: cambiar de camino es cambiar un campo
(`provider: "off"` o `"on"`).

> **Pix, para quien viene del SIP o de Transferencias 3.0.** Pix es el sistema
> de pago instantáneo del Banco Central de Brasil — la idea es la misma que
> las transferencias instantáneas y el QR de su país, pero el QR brasileño
> puede **estar atado a un boleto**: cuando el cliente paga el QR, el título se
> da de baja solo. Eso es el Bolepix.

---

## El primer boleto, en cinco minutos

Sin cuenta, sin credencial, sin registro — el camino offline funciona con
datos de prueba:

```bash
docker run -p 8000:8000 ghcr.io/maxwbh/cobranca-api:latest
```

```bash
curl -G http://localhost:8000/api/boleto \
  --data-urlencode 'bank=banco_brasil' \
  --data-urlencode 'type=pdf' \
  --data-urlencode 'data={"valor":1500.00,"cedente":"Empresa LTDA","documento_cedente":"11222333000181","sacado":"Joao da Silva","sacado_documento":"52998224725","agencia":"3073","conta_corrente":"12345678","convenio":"1234567","carteira":"18","nosso_numero":"123","data_vencimento":"2027-12-31"}' \
  -o boleto.pdf
```

Eso devuelve un PDF válido para imprimir. Para que el banco lo **cobre**, los
datos de cuenta tienen que ser los suyos y el título tiene que ir en la
remesa CNAB — o registrarse por el camino online.

La documentación interactiva queda en `http://localhost:8000/docs` (gateway) y
`http://localhost:8000/api/docs` (offline), con el botón *Try it out* apuntando
a su propia instancia. **Ambas hablan español:** agregue `?lang=es` a la URL,
o deje que el navegador mande su `Accept-Language` — la referencia es la misma
spec, con las descripciones traducidas. Sin servidor, la copia publicada está
en el [Swagger en español](../swagger/es/).

**Los errores también.** Con el header `Accept-Language: es` (o `lang=es` en
la query), toda respuesta de error vuelve con los mensajes en español — el
nombre del campo, el código HTTP y las claves del JSON no cambian:

```json
{"error": "Datos del boleto inválidos",
 "validation_errors": ["sacado_documento: CPF/CNPJ brasileño inválido"]}
```

Y el **retorno CNAB** — lo que el banco devuelve diciendo qué se pagó — sale
también como tabla: `POST /api/retorno?formato=csv` devuelve un CSV con el
encabezado en español para la contabilidad, con las mismas diez columnas del
JSON.

Hay scripts listos, que corren contra su container, en
[PHP](https://github.com/Maxwbh/cobranca-api/tree/main/examples/php) y en
[Python](https://github.com/Maxwbh/cobranca-api/tree/main/examples/python):
una cobranza con PDF, doce boletos de prueba con y sin QR Pix, y una remesa
CNAB.

---

## Glosario — el vocabulario de la API, en español

Los nombres de campo son **en portugués y no cambian**: son el contrato de la
API, y traducirlos rompería a quien ya integró. Esta tabla cubre **todos los
campos** del boleto (el esquema `BoletoData` del Swagger), para que ninguno lo
sorprenda.

### Los seis obligatorios

| Campo | En español | Nota |
|---|---|---|
| `cedente` | **Beneficiario** — quien cobra | Razón social de su empresa |
| `documento_cedente` | CNPJ/CPF del beneficiario | Su documento brasileño. Sin él no hay boleto |
| `sacado` | **Pagador** — quien paga | Nombre del cliente |
| `sacado_documento` | CPF/CNPJ del pagador | Documento brasileño del cliente. Equivale a CI/RUC/CUIT, pero tiene que ser el brasileño |
| `nosso_numero` | "Nuestro número" — identificador del título | Número que **usted** asigna según las reglas del banco; va dentro del código de barras |
| `valor` | Importe | En reales (BRL), decimal con punto |

### La cuenta bancaria

| Campo | En español | Nota |
|---|---|---|
| `agencia` | Sucursal (agência) | Sin dígito verificador |
| `digito_agencia` | DV de la sucursal | Obligatorio en **Safra** |
| `conta_corrente` | Cuenta corriente | — |
| `digito_conta` | DV de la cuenta | Obligatorio en **Unicred**, **Banco do Nordeste**, **Banestes** y **Safra** |
| `convenio` | Convenio de cobranza | El número que el banco le dio al habilitar cobrança |
| `digito_convenio` | DV del convenio | Lo imprime el **Banrisul** |
| `carteira` | Cartera | Modalidad de cobranza, definida por el banco |
| `variacao` | Variación de la cartera | **Banestes**, **Sicoob** |
| `posto` | Puesto de la cooperativa | **Sicredi** |
| `byte_idt` | Byte identificador | Parte del nosso número; obligatorio en **Sicredi** |
| `incremento` | Incremento | Tres posiciones del campo libre; obligatorio en **BRB** |
| `portfolio` | Portafolio | Tres posiciones del campo libre, **Citibank**. Sin él el código sale con ceros, sin error |

### Fechas, documento e importes

| Campo | En español | Nota |
|---|---|---|
| `data_vencimento` | Fecha de vencimiento | `AAAA-MM-DD` |
| `data_documento` | Fecha de emisión | Obligatoria en **Sicredi** |
| `numero_documento` | Número del documento | Su número de factura, impreso en la ficha |
| `especie_documento` | Tipo de documento | `DM` duplicata mercantil (factura), `NP` pagaré, `RC` recibo… Default `DM` |
| `especie_moeda` | Moneda impresa | Default `R$`. **Solo cambia el rótulo**: el importe es siempre en reales |
| `aceite` | Aceptación del pagador | `S`/`N`. Default `N` |
| `quantidade` | Cantidad de cuotas del carnet | En **Sicoob** entra en el código de barras |
| `mora_multa` | Mora y multa | ⚠️ Aceptado y **no impreso**: la franja FEBRABAN la llena el cajero. El valor va en la remesa CNAB |
| `desconto_abatimento` | Descuento / rebaja | ⚠️ Ídem |
| `outras_deducoes` | Otras deducciones | ⚠️ Ídem |
| `outros_acrescimos` | Otros recargos | ⚠️ Ídem |
| `valor_cobrado` | Importe cobrado | ⚠️ Ídem |

### Texto en la ficha

| Campo | En español | Nota |
|---|---|---|
| `instrucoes` | Instrucciones al cajero | Lista de líneas o texto con saltos. **Es el campo que se dibuja** |
| `instrucao1` … `instrucao6` | Instrucción 1 a 6 | Se juntan en orden y pasan a ser `instrucoes`; no mande las dos formas |
| `demonstrativo` | Detalle / demostrativo | Mismas reglas que `instrucoes` |
| `local_pagamento` | Lugar de pago | Default: *"Pagável em qualquer banco até o vencimento"* |
| `cedente_endereco` | Dirección del beneficiario | Impresa bajo el nombre |
| `sacado_endereco` | Dirección del pagador | Completa |
| `sacador_avalista` | Librador / avalista | Campo propio de la ficha |
| `external_id` | Identificador externo | ⚠️ No se imprime: identifica el ítem **dentro de un lote** |
| `seu_numero` | "Su número" | ⚠️ Misma función que `external_id` |

### Marca de la empresa (modelo `moderno` y factura)

| Campo | En español | Nota |
|---|---|---|
| `logo_empresa` | Marca del beneficiario | **Texto**, no archivo |
| `cor_marca` | Color de la marca | Hex `RRGGBB` |
| `marca_dagua` | Marca de agua | Antifraude, diagonal |
| `rodape_contato` | Pie con el contacto | — |
| `parcela_atual` | Cuota actual | Sello "Cuota n/N"; va con `total_parcelas` |
| `total_parcelas` | Total de cuotas | — |

### Pix en el boleto

| Campo | En español | Nota |
|---|---|---|
| `chave_pix` | Clave Pix | CPF, CNPJ, email, teléfono o aleatoria. Genera un QR en el PDF. ⚠️ **Ese QR no es Bolepix**: cobra a la clave, no da de baja el título |
| `tipo_chave_pix` | Tipo de clave | Aceptado y descartado — se deduce de la clave |
| `txid` | ID de la transacción Pix | Hasta 25 alfanuméricos; va dentro del QR |
| `pix_observacao` | Observación del Pix | Hasta 40 caracteres, visible al pagador |
| `pix_copia_cola` | Pix "copia y pega" | El payload que el **banco** devolvió al registrar — ese sí es Bolepix |

### Aceptados y no usados — o que responden 400

| Campo | Qué pasa |
|---|---|
| `codigo_barras`, `linha_digitavel` | Aceptados y **conferidos, no usados**: el código se calcula localmente; estos solo avisan si el del banco difiere |
| `cedente_cidade`, `numero_contrato` | Aceptados y **no dibujados** en ningún modelo |
| `logo` | **400.** Es el logo del **banco**, que ya viene. La marca de su empresa es `logo_empresa` |
| `emv`, `fonte_ttf`, `pix_label` | **400.** Nunca tuvieron efecto; quedaron del esquema antiguo |

---

## Los términos que va a leer en portugués

| Portugués | Español |
|---|---|
| boleto bancário | boleto bancario — ficha con código de barras pagable en cualquier banco o app de Brasil hasta el vencimiento |
| linha digitável | línea digitable — el código de barras en números, para pagar tecleando |
| carnê | carnet / talonario de cuotas |
| remessa / retorno | archivo de remesa (usted → banco) / archivo de retorno (banco → usted), en formato CNAB |
| cobrança registrada | cobranza registrada — el título existe en el banco antes de que el cliente pague |
| baixa | baja del título |
| liquidação | liquidación — el pago efectivo |
| conciliação | conciliación |
| extrato | extracto bancario |
| convênio | convenio de cobranza |
| cofre de credenciais | bóveda de credenciales — donde la API guarda la credencial del banco, por cliente (`tenant_id`) |

---

## Dónde seguir

- [**¿Por qué sin intermediario?**](comercial.md) — el argumento comercial: MIT, en su servidor, sin comisión por venta
- [**Swagger en español**](../swagger/es/) — la referencia completa, generada del código
- [**Swagger — gateway**](../swagger/) — todas las rutas online y offline (portugués)
- [**Swagger — offline**](../swagger/offline.html) — boleto, CNAB y OFX sin convenio (portugués)
- [Guía de despliegue](../deploy.md) — qué pide el servicio del host, variables, persistencia
- [Código en GitHub](https://github.com/Maxwbh/cobranca-api)

Desarrollado por **Maxwell da Silva Oliveira** —
[M&S do Brasil LTDA](https://msbrasil.inf.br). Consultas sobre integración
bancaria en Brasil, Oracle APEX y Python: [hablemos](https://msbrasil.inf.br).
