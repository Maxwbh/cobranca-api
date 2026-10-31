---
title: Cobre en Brasil sin intermediario
description: Para empresas del Mercosur que venden a brasileños — boleto, Pix y CNAB en reales con una API open source, instalada en su servidor, sin comisión por venta.
lang: es
---

# Cobre en Brasil sin intermediario

**Usted vende a brasileños. Ellos pagan como pagan en Brasil: boleto o Pix,
en reales.** Entre su sistema y el banco brasileño hoy suele haber un
intermediario que cobra un porcentaje por cada venta y guarda sus datos de
cobranza en una plataforma que no es suya.

La Cobranca-API es la otra opción: **software libre (MIT), instalado en su
propio servidor, que habla con el banco brasileño por usted.** No cobra por
venta porque no es un servicio: es un programa.

---

## Qué cambia

| | Con intermediario (PSP / gateway de pagos) | Con la Cobranca-API |
|---|---|---|
| Costo por venta | Porcentaje + tarifa fija, en cada boleto o Pix | **Cero.** Solo lo que su banco cobra por el convenio |
| Dónde viven los datos | En la plataforma del intermediario | **En su servidor** — un container Docker |
| Dependencia | De un proveedor, su contrato y su API | Del banco donde está su cuenta. El código es suyo |
| Bancos | Los que el intermediario eligió | 4 online (C6, Sicoob, Inter, Itaú) y 19 por archivo CNAB |
| Integración | SDK del proveedor | **HTTP** desde PHP, Java, C#, Node, Python o lo que use |
| Cuándo deja de funcionar | Cuando el proveedor cambia de reglas | Cuando usted lo apague |

---

## Qué necesita

Tres cosas, y ninguna es software:

1. **Una empresa con CNPJ en Brasil** (o una persona con CPF). El boleto y el
   Pix se emiten a nombre de un contribuyente brasileño.
2. **Una cuenta en un banco brasileño**, con el servicio de cobranza
   habilitado — el banco le da un *convenio* y una *cartera*.
3. **El CPF o CNPJ de cada cliente.** Es cómo el sistema bancario brasileño
   identifica al pagador. Cédula, RUC o CUIT no sirven, y la API lo dice con
   un error claro.

La apertura — empresa, cuenta y convenio — es un **trámite**, y
[M&S do Brasil](https://msbrasil.inf.br) lo acompaña como servicio, junto con
la integración a su sistema. La API no cambia esa barrera; la deja explícita
desde el primer día.

---

## Cómo se ve en la práctica

Un `docker run` en su servidor y la API responde en `localhost:8000`. Su
sistema hace un `POST /cobranca` con los datos del título; la API devuelve la
línea digitable, el código de barras y el PDF — o registra el título en el
banco y devuelve el QR Pix vinculado (**Bolepix**), que al pagarse da de baja
el título solo.

Para cobrar por archivo (el camino que no exige credencial de API del banco),
la misma API genera la **remesa CNAB** que usted sube al portal del banco y
lee el **retorno** que el banco devuelve, diciéndole qué se pagó.

Todo esto ya funciona hoy, en portugués, para empresas brasileñas. Lo que esta
página y la [guía en español](./) agregan es que la API **se explique** a quien
está del otro lado de la frontera: glosario de todos los campos, mensajes de
error en español (`Accept-Language: es`), referencia Swagger en español y
ejemplos listos en PHP y Python.

---

## Lo que esto no es

- **No es una pasarela de pagos.** No hay cuenta en la Cobranca-API, no hay
  saldo, no hay liquidación hacia su país. El dinero entra en **su** cuenta
  en Brasil, y moverlo de ahí es asunto suyo y de su banco.
- **No convierte moneda.** Todo es en reales. Si quiere mostrar la
  referencia en guaraníes, pesos o dólares, va en el texto de instrucciones
  del boleto.
- **No integra el sistema de pagos de su país.** SIP, QR Hub, Transferencias
  3.0: ninguno entra mientras no haya una API pública del banco central y un
  cliente que reciba en moneda local.

---

## Dónde seguir

- [**Guía en español**](./) — qué necesita antes, los dos caminos, el primer boleto y el glosario de campos
- [**Swagger en español**](../swagger/es/) — toda la referencia, generada del código
- [Ejemplos en PHP](https://github.com/Maxwbh/cobranca-api/tree/main/examples/php) y en [Python](https://github.com/Maxwbh/cobranca-api/tree/main/examples/python)
- [Código en GitHub](https://github.com/Maxwbh/cobranca-api) — licencia MIT

**Para hablar de la integración:** [M&S do Brasil LTDA](https://msbrasil.inf.br),
de Maxwell da Silva Oliveira — integración bancaria en Brasil, Oracle APEX y
Python.
