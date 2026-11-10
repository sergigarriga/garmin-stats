"""Login con Google para la web (Lambda detrás de CloudFront, ruta /auth/*).

Flujo OAuth "authorization code" + PKCE. El id_token llega directamente de Google por TLS, así que
basta con comprobar emisor, audiencia, caducidad y email (lo permite la especificación de OpenID).
Si el email está en el registro de usuarias (S3 admin/users.json, lo gestiona el dueño desde la web),
pone la cookie de sesión `gs_session` firmada con HMAC, que la CloudFront Function comprueba antes de
servir cualquier archivo (y con la que sirve a cada persona solo su carpeta de datos).
Solo usa la librería estándar (y boto3, incluido en Lambda).
"""

import base64
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import time
import urllib.parse
import urllib.request

import boto3

OWNER = os.environ["OWNER_EMAIL"].strip().lower()
BUCKET = os.environ["BUCKET"]
USERS_KEY = "admin/users.json"
SESSION_SECRET = os.environ["SESSION_SECRET"].encode()
ORIGIN_SECRET = os.environ["ORIGIN_SECRET"]
CLIENT_ID_PARAM = os.environ["GOOGLE_CLIENT_ID_PARAM"]
CLIENT_SECRET_PARAM = os.environ["GOOGLE_CLIENT_SECRET_PARAM"]
SESSION_DAYS = 30
_ssm = boto3.client("ssm")
_s3 = boto3.client("s3")
_cfg: dict = {}


def _check_user(email: str, name: str) -> bool:
    """¿Tiene invitación? Al entrar por primera vez se apunta su nombre y la fecha."""
    try:
        reg = json.loads(_s3.get_object(Bucket=BUCKET, Key=USERS_KEY)["Body"].read())
    except _s3.exceptions.NoSuchKey:
        reg = {"users": []}
    users = reg.setdefault("users", [])
    u = next((x for x in users if x.get("email") == email), None)
    if u is None and email == OWNER:  # arranque: el dueño siempre puede entrar
        uid = hmac.new(SESSION_SECRET, b"uid:" + email.encode(), hashlib.sha256).hexdigest()[:16]
        u = {"email": email, "uid": uid, "name": name, "role": "owner", "budgetUsd": 50, "status": "onboarding",
             "invitedAt": int(time.time())}
        users.append(u)
    if u is None:
        return False
    changed = False
    if u.get("status") == "invited":
        u["status"], changed = "onboarding", True
    if not u.get("joinedAt"):
        u["joinedAt"], changed = int(time.time()), True
    if name and not u.get("name"):
        u["name"], changed = name, True
    if changed:
        _s3.put_object(Bucket=BUCKET, Key=USERS_KEY, Body=json.dumps(reg, ensure_ascii=False, indent=1).encode(),
                       ContentType="application/json")
    return True


def _google():
    if not _cfg:
        try:
            _cfg["id"] = _ssm.get_parameter(Name=CLIENT_ID_PARAM)["Parameter"]["Value"]
            _cfg["secret"] = _ssm.get_parameter(Name=CLIENT_SECRET_PARAM, WithDecryption=True)["Parameter"]["Value"]
        except _ssm.exceptions.ParameterNotFound:
            return None
    return _cfg


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def session_cookie(email: str) -> str:
    exp = int(time.time()) + SESSION_DAYS * 86400
    payload = f"{_b64(email.encode())}.{exp}"
    mac = hmac.new(SESSION_SECRET, payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{mac}"


def _resp(status, body="", headers=None, cookies=None, ctype="text/html; charset=utf-8"):
    h = {"content-type": ctype, "cache-control": "no-store", "referrer-policy": "no-referrer"}
    h.update(headers or {})
    return {"statusCode": status, "headers": h, "cookies": cookies or [], "body": body}


G_LOGO = ('<svg width="20" height="20" viewBox="0 0 48 48" aria-hidden="true"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 '
          '9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>'
          '<path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 '
          '7.09-10.36 7.09-17.65z"/><path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 '
          '16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/><path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c'
          '-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/></svg>')

LOGO_LIGHT = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="16 -1302 6423 1436"><g fill="#5A6B32"><path transform="rotate(-6 621 -449) translate(0 30) scale(1 -1)" d="M422.3067626953125 -43.600830078125Q365.60546875 -43.600830078125 322.0045166015625 -30.05072021484375Q278.403564453125 -16.5006103515625 245.65289306640625 8.14959716796875Q212.9022216796875 32.7998046875 187.001708984375 66.5001220703125Q159.7012939453125 103.7000732421875 138.85101318359375 149.89990234375Q118.000732421875 196.0997314453125 104.15057373046875 248.099609375Q90.3004150390625 300.0994873046875 83.15032958984375 355.74957275390625Q76.000244140625 411.399658203125 76.000244140625 466.60009765625Q76.000244140625 635.600341796875 153.801025390625 754.900634765625Q231.601806640625 874.200927734375 368.85284423828125 937.8011474609375Q506.1038818359375 1001.4013671875 684.004638671875 1001.4013671875Q773.005615234375 1001.4013671875 859.0067138671875 986.3511352539062Q945.0078125 971.3009033203125 1014.1587524414062 939.600341796875Q1083.3096923828125 907.8997802734375 1124.8602905273438 858.4487915039062Q1166.410888671875 808.997802734375 1166.410888671875 740.0963134765625Q1166.410888671875 672.99462890625 1139.5602416992188 635.59375Q1112.7095947265625 598.19287109375 1070.3585815429688 583.9425659179688Q1028.007568359375 569.6922607421875 982.406494140625 569.6922607421875Q917.1055908203125 569.6922607421875 866.40576171875 583.0921630859375Q815.7059326171875 596.4920654296875 753.1070556640625 596.4920654296875Q695.9105224609375 596.4920654296875 658.61181640625 564.5943603515625Q621.3131103515625 532.6966552734375 621.3131103515625 459.2996826171875Q621.3131103515625 429.5006103515625 624.1630249023438 400.6014404296875Q627.012939453125 371.7022705078125 631.5128173828125 344.35296630859375Q636.0126953125 317.003662109375 640.4625854492188 290.2041015625Q644.9124755859375 263.404541015625 647.7623901367188 238.75469970703125Q650.6123046875 214.1048583984375 650.6123046875 190.20458984375Q650.6123046875 73.60205078125 596.2610473632812 15.0006103515625Q541.9097900390625 -43.600830078125 422.3067626953125 -43.600830078125Z"/><path transform="rotate(3 1817 -455) translate(1101 -25) scale(1 -1)" d="M723.3065185546875 -76.00048828125Q559.1055908203125 -76.00048828125 429.8043212890625 -38.2008056640625Q300.5030517578125 -0.401123046875 210.45184326171875 75.5985107421875Q120.400634765625 151.59814453125 73.1998291015625 267.998046875Q25.9990234375 384.39794921875 25.9990234375 541.6983642578125Q25.9990234375 584.4986572265625 30.9991455078125 624.7488403320312Q35.999267578125 664.9990234375 46.49951171875 701.4991455078125Q56.999755859375 737.999267578125 71.60009765625 769.199462890625Q109.0009765625 847.39990234375 176.15252685546875 891.3505249023438Q243.3040771484375 935.3011474609375 337.5062255859375 935.3011474609375Q430.5084228515625 935.3011474609375 476.55950927734375 907.1007080078125Q522.610595703125 878.9002685546875 538.510986328125 837.399658203125Q554.411376953125 795.8990478515625 556.21142578125 756.8985595703125Q558.011474609375 731.8983154296875 559.2615356445312 707.9984130859375Q560.5115966796875 684.0985107421875 562.211669921875 661.5487670898438Q563.9117431640625 638.9990234375 566.0618286132812 618.3493041992188Q568.2119140625 597.6995849609375 570.9119873046875 579.0997314453125Q581.7122802734375 503.2021484375 601.4619750976562 454.85443115234375Q621.211669921875 406.5067138671875 654.6604614257812 383.05816650390625Q688.1092529296875 359.609619140625 738.1068115234375 359.609619140625Q776.8037109375 359.609619140625 808.4522094726562 377.5084228515625Q840.1007080078125 395.4072265625 863.7001953125 436.3052978515625Q887.2996826171875 477.203369140625 901.799560546875 545.3011474609375Q908.4996337890625 573.60107421875 911.9996337890625 600.90087890625Q915.4996337890625 628.20068359375 917.9996337890625 654.7504272460938Q920.4996337890625 681.3001708984375 925.2496948242188 707.5498657226562Q929.999755859375 733.799560546875 938.199951171875 759.999267578125Q961.800537109375 827.4993896484375 1017.0518188476562 870.2496948242188Q1072.3031005859375 913 1175.3052978515625 913Q1266.00732421875 913 1314.7584838867188 866.3493041992188Q1363.5096435546875 819.6986083984375 1385.1102294921875 741.6976318359375Q1391.410400390625 714.8980712890625 1395.7605590820312 685.4984130859375Q1400.1107177734375 656.0987548828125 1402.1608276367188 624.5989990234375Q1404.2109375 593.0992431640625 1405.2110595703125 560.3994140625Q1406.211181640625 527.6995849609375 1405.7113037109375 494.2996826171875Q1403.7117919921875 290.0987548828125 1316.5108642578125 164.44879150390625Q1229.3099365234375 38.798828125 1076.30859375 -18.600830078125Q923.3072509765625 -76.00048828125 723.3065185546875 -76.00048828125Z"/><path transform="rotate(-3 3200 -440) translate(2499 15) scale(1 -1)" d="M273.3052978515625 -22Q186.803466796875 -22 129.5020751953125 7.6002197265625Q72.20068359375 37.200439453125 43.39990234375 105.0009765625Q35.2996826171875 125.9007568359375 30.49951171875 151.35040283203125Q25.6993408203125 176.800048828125 23.34918212890625 207.04949951171875Q20.9990234375 237.2989501953125 21.598876953125 271.398193359375Q23.4984130859375 480.398681640625 109.34918212890625 628.1491088867188Q195.199951171875 775.8995361328125 346.35125732421875 854.2998046875Q497.5025634765625 932.7000732421875 692.7037353515625 932.7000732421875Q890.5050048828125 932.7000732421875 1045.6565551757812 856.0997314453125Q1200.80810546875 779.4993896484375 1290.209228515625 634.3992919921875Q1379.6103515625 489.2991943359375 1379.6103515625 285Q1379.6103515625 253.400390625 1376.01025390625 224.85064697265625Q1372.41015625 196.3009033203125 1365.6099853515625 170.801025390625Q1358.809814453125 145.3011474609375 1348.7095947265625 122.3011474609375Q1317.7088623046875 53.3009033203125 1258.407470703125 15.65045166015625Q1199.1060791015625 -22 1119.20458984375 -22Q1022.602294921875 -22 969.4010009765625 2.85040283203125Q916.19970703125 27.7008056640625 892.6491088867188 74.4014892578125Q869.0985107421875 121.1021728515625 859.1982421875 185.7030029296875Q852.8980712890625 234.601806640625 846.9979248046875 274.45098876953125Q841.0977783203125 314.3001708984375 834.4976806640625 345.94952392578125Q827.8975830078125 377.598876953125 821.49755859375 402.84820556640625Q815.0975341796875 428.0975341796875 807.6976318359375 448.796630859375Q790.597900390625 496.0941162109375 766.4492797851562 515.9425659179688Q742.3006591796875 535.791015625 704.203857421875 535.791015625Q671.7071533203125 535.791015625 647.4589233398438 515.292724609375Q623.210693359375 494.79443359375 604.21142578125 449.4969482421875Q595.1116943359375 427.597900390625 586.811767578125 399.69873046875Q578.5118408203125 371.799560546875 571.1618041992188 336.6002197265625Q563.811767578125 301.40087890625 557.2616577148438 258.75140380859375Q550.7115478515625 216.1019287109375 543.3114013671875 164.7022705078125Q533.3111572265625 91.1014404296875 494.1102294921875 50.6009521484375Q454.9093017578125 10.1004638671875 397.75799560546875 -5.94976806640625Q340.606689453125 -22 273.3052978515625 -22Z"/><path transform="rotate(4 4475 -512) translate(3878 -20) scale(1 -1)" d="M678.00341796875 -79.3009033203125Q549.0029296875 -79.3009033203125 432.90234375 -50.60107421875Q316.8017578125 -21.9012451171875 226.501220703125 41.64874267578125Q136.20068359375 105.19873046875 84.600341796875 207.74908447265625Q33 310.2994384765625 33 458.9005126953125Q33 610.3013916015625 76.65008544921875 723.2017822265625Q120.3001708984375 836.1021728515625 205.00048828125 912.102294921875Q289.7008056640625 988.1024169921875 413.00146484375 1025.7523803710938Q536.3021240234375 1063.40234375 694.603271484375 1063.40234375Q822.804443359375 1063.40234375 903.7548217773438 1035.4019775390625Q984.7052001953125 1007.401611328125 1023.2551879882812 961.7509155273438Q1061.80517578125 916.1002197265625 1061.80517578125 862.19921875Q1061.80517578125 820.2982177734375 1040.3046875 786.097412109375Q1018.80419921875 751.8966064453125 984.9034423828125 732.296142578125Q951.002685546875 712.6956787109375 914.201904296875 712.6956787109375Q882.801513671875 712.6956787109375 856.2515258789062 719.2955322265625Q829.7015380859375 725.8953857421875 796.9519653320312 732.4952392578125Q764.202392578125 739.0950927734375 714.603271484375 739.0950927734375Q673.205078125 739.0950927734375 639.1565551757812 725.6956787109375Q605.1080322265625 712.2962646484375 579.7590942382812 686.997314453125Q554.41015625 661.6983642578125 540.5607299804688 626.4497680664062Q526.7113037109375 591.201171875 526.7113037109375 548.3028564453125Q526.7113037109375 480.1046142578125 547.9602661132812 437.85601806640625Q569.209228515625 395.607421875 610.2576293945312 376.208251953125Q651.3060302734375 356.80908203125 710.204345703125 356.80908203125Q751.002197265625 356.80908203125 792.30126953125 363.85858154296875Q833.600341796875 370.9080810546875 872.1502075195312 380.607421875Q910.7000732421875 390.3067626953125 941.9002685546875 397.35626220703125Q973.1004638671875 404.40576171875 992.800537109375 404.40576171875Q1056.9019775390625 404.40576171875 1093.8028564453125 375.205078125Q1130.7037353515625 346.00439453125 1146.1541137695312 303.15338134765625Q1161.6044921875 260.3023681640625 1161.6044921875 219.3013916015625Q1161.6044921875 140.0997314453125 1123.4041748046875 83.4991455078125Q1085.203857421875 26.8985595703125 1018.603515625 -9.201416015625Q952.003173828125 -45.3013916015625 864.403076171875 -62.3011474609375Q776.802978515625 -79.3009033203125 678.00341796875 -79.3009033203125Z"/><path transform="rotate(-2 5725 -591) translate(5043 10) scale(1 -1)" d="M250.803955078125 -50Q175.9022216796875 -50 134.7012939453125 -19.24957275390625Q93.5003662109375 11.5008544921875 69.8997802734375 65.80126953125Q60.799560546875 87.201171875 53.4993896484375 122.35076904296875Q46.19921875 157.5003662109375 40.24908447265625 202.94964599609375Q34.2989501953125 248.39892578125 31.14886474609375 300.6978759765625Q27.998779296875 352.996826171875 27.998779296875 408.6954345703125Q27.998779296875 482.0958251953125 34.84893798828125 556.9461059570312Q41.6990966796875 631.79638671875 55.8994140625 704.3966064453125Q70.0997314453125 776.996826171875 92.000244140625 845.6470336914062Q113.9007568359375 914.2972412109375 143.95147705078125 976.2974853515625Q174.002197265625 1038.2977294921875 212.203125 1091.798095703125Q267.6044921875 1167.6988525390625 340.55621337890625 1209.8494262695312Q413.5079345703125 1252 506.3101806640625 1252Q601.3123779296875 1252 658.5637817382812 1196.8990478515625Q715.815185546875 1141.798095703125 715.815185546875 1047.796875Q715.815185546875 1018.4971923828125 710.2650756835938 987.5477905273438Q704.7149658203125 956.598388671875 696.8148193359375 927.1491088867188Q688.9146728515625 897.6998291015625 681.41455078125 870.800537109375Q673.9144287109375 843.9012451171875 668.3643188476562 823.0518188476562Q662.814208984375 802.202392578125 662.814208984375 790.002685546875Q662.814208984375 772.603271484375 676.5142822265625 772.603271484375Q692.5145263671875 772.603271484375 712.0643920898438 784.0526733398438Q731.6142578125 795.5020751953125 760.1136474609375 810.6513061523438Q788.613037109375 825.800537109375 832.0619506835938 837.2499389648438Q875.5108642578125 848.6993408203125 939.3092041015625 848.6993408203125Q1052.609375 848.6993408203125 1128.8595581054688 811.1494750976562Q1205.1097412109375 773.599609375 1250.909912109375 708.19970703125Q1296.7100830078125 642.7998046875 1316.3601684570312 559.1497192382812Q1336.01025390625 475.4996337890625 1336.01025390625 383.2991943359375Q1336.01025390625 340.59912109375 1332.2603149414062 298.99951171875Q1328.5103759765625 257.39990234375 1321.6104736328125 220.35052490234375Q1314.7105712890625 183.3011474609375 1304.8606567382812 151.9017333984375Q1295.0107421875 120.5023193359375 1282.7108154296875 97.402587890625Q1248.7100830078125 35.5013427734375 1188.0086669921875 3.75067138671875Q1127.3072509765625 -28 1036.205078125 -28Q961.603271484375 -28 920.30224609375 -1.49951171875Q879.001220703125 25.0009765625 857.400634765625 73.7020263671875Q849.3004150390625 94.7020263671875 843.7500610351562 121.25152587890625Q838.19970703125 147.801025390625 834.29931640625 179.35028076171875Q830.39892578125 210.8995361328125 827.0986328125 245.5987548828125Q823.79833984375 280.2979736328125 820.1982421875 316.597412109375Q816.59814453125 351.6966552734375 810.3483276367188 379.2955322265625Q804.0985107421875 406.8944091796875 792.8990478515625 425.9932861328125Q781.6995849609375 445.0921630859375 762.6505737304688 455.5914306640625Q743.6015625 466.0906982421875 714.3031005859375 466.0906982421875Q686.00537109375 466.0906982421875 664.0570678710938 457.64154052734375Q642.1087646484375 449.1923828125 625.7098388671875 433.3935546875Q609.3109130859375 417.5947265625 597.0613403320312 395.44573974609375Q584.811767578125 373.2967529296875 576.7115478515625 345.9970703125Q564.1112060546875 301.8980712890625 553.6609497070312 267.0989990234375Q543.210693359375 232.2999267578125 533.0604858398438 202.45062255859375Q522.9102783203125 172.601318359375 510.9100341796875 143.3016357421875Q498.9097900390625 114.001953125 483.20947265625 80.7017822265625Q451.3087158203125 17.9010009765625 393.00732421875 -16.04949951171875Q334.7059326171875 -50 250.803955078125 -50Z"/></g></svg>"""

# El logotipo, una sola vez por página y con el color del tema (currentColor). Las coordenadas se redondean a enteros
# (el dibujo mide 6423 unidades de ancho: no se nota) para que la página pese menos de la mitad.
_LOGO_SVG = re.sub(r"\d+\.\d+", lambda m: str(round(float(m.group()))), LOGO_LIGHT)
LOGO = _LOGO_SVG.replace('<g fill="#5A6B32">', '<g fill="currentColor">').replace("<svg ", '<svg aria-hidden="true" focusable="false" ', 1)

# Fondo: el logotipo repetido en filas, muy suave. Es el mismo dibujo (trazados, no una fuente) usado como máscara
# CSS en un data URI: no pide nada a la red y toma el color del tema.
_WM_TILE = urllib.parse.quote(
    _LOGO_SVG.replace('viewBox="16 -1302 6423 1436"', 'viewBox="16 -1302 7900 1436"').replace('"', "'"),
    safe=" '/:=().,-")
BG = '<div class="bg" aria-hidden="true">' + "<i></i>" * 14 + "</div>"

BASE_CSS = """
:root{--bg:#F6F4EE;--card:#FFFFFF;--text:#1F1F1F;--muted:#444746;--line:#E6E2D8;--brand:#5A6B32;--logo:#5A6B32;--motif:#5A6B32;--mo:.09;
 --note:#EEF1E4;--btn:#FFFFFF;--btnText:#1F1F1F;--btnLine:#747775;--shadow:0 1px 2px rgba(70,84,42,.06),0 12px 40px rgba(70,84,42,.10);
 --wm:url("data:image/svg+xml,""" + _WM_TILE + """")}
@media (prefers-color-scheme:dark){:root{--bg:#0E0E0F;--card:#1E1F20;--text:#E3E3E3;--muted:#C4C7C5;--line:#333537;--brand:#B4C784;--logo:#F7F3EC;
 --motif:#B4C784;--mo:.07;--note:#2A2F22;--btn:#131314;--btnText:#E3E3E3;--btnLine:#8E918F;--shadow:0 12px 40px rgba(0,0,0,.5)}}
*{box-sizing:border-box}
html{background:var(--bg);-webkit-text-size-adjust:100%;text-size-adjust:100%;overscroll-behavior:none}
body{margin:0;background:var(--bg);color:var(--text);overscroll-behavior:none;-webkit-tap-highlight-color:transparent;
 font:16px/1.55 "Google Sans Flex","Google Sans",Roboto,system-ui,-apple-system,"Segoe UI",sans-serif}
a{color:var(--brand);text-underline-offset:.18em}
a:focus-visible{outline:3px solid var(--brand);outline-offset:3px;border-radius:6px}
.wm{display:inline-flex;color:var(--logo)}.wm svg{display:block;width:auto;height:100%}
.bg{position:fixed;inset:0;z-index:0;overflow:hidden;pointer-events:none;-webkit-user-select:none;user-select:none;
 --h:clamp(54px,16vw,116px);display:flex;flex-direction:column;justify-content:center;gap:calc(var(--h)*.34);opacity:var(--mo)}
.bg i{flex:none;display:block;height:var(--h);background:var(--motif);opacity:var(--o,1);
 -webkit-mask:var(--wm) calc(var(--h)*var(--x,0)) 0/auto 100% repeat-x;mask:var(--wm) calc(var(--h)*var(--x,0)) 0/auto 100% repeat-x}
.bg i:nth-child(even){--x:-2.3}.bg i:nth-child(odd){--x:.45}
.bg i:nth-child(3n){--o:.6}.bg i:nth-child(4n+1){--o:.8}.bg i:nth-child(7n+2){--o:.45}
"""

CSS = BASE_CSS + """
html,body{min-height:100%}
body{min-height:100vh;min-height:100dvh;display:flex;flex-direction:column;align-items:center;overflow-x:hidden;touch-action:manipulation;
 padding:max(20px,env(safe-area-inset-top)) max(16px,env(safe-area-inset-right)) max(14px,env(safe-area-inset-bottom)) max(16px,env(safe-area-inset-left))}
main{position:relative;z-index:1;flex:1;width:100%;display:flex;align-items:center;justify-content:center;padding:8px 0 20px}
.card{width:100%;max-width:408px;background:var(--card);border:1px solid var(--line);border-radius:32px;box-shadow:var(--shadow);
 padding:clamp(28px,7vw,40px) clamp(22px,6vw,36px) clamp(24px,6vw,32px);text-align:center}
.card .wm{height:clamp(44px,13vw,56px);margin:0 auto 22px}
h1{font-size:clamp(24px,6.6vw,28px);line-height:1.15;font-weight:500;letter-spacing:-.02em;margin:0 0 10px;text-wrap:balance}
h1 em{font-style:normal;color:var(--brand)}
.lead{color:var(--muted);font-size:16px;line-height:1.5;margin:0 0 24px;text-wrap:pretty}
.msg{background:var(--note);border-radius:16px;padding:12px 16px;margin:0 0 16px;font-size:15px;line-height:1.45;overflow-wrap:anywhere}
.btn{display:flex;align-items:center;justify-content:center;gap:12px;min-height:54px;padding:8px 24px;border-radius:999px;width:100%;
 background:var(--btn);color:var(--btnText);border:1px solid var(--btnLine);text-decoration:none;font-weight:500;font-size:16px;
 transition:box-shadow .2s,transform .2s}
.btn svg{flex:none}
.btn:hover{box-shadow:0 1px 3px rgba(0,0,0,.14),0 6px 16px rgba(0,0,0,.10)}.btn:active{transform:scale(.985)}
.btn:focus-visible{outline:3px solid var(--brand);outline-offset:3px;border-radius:999px}
.note{display:flex;gap:8px;align-items:flex-start;justify-content:center;color:var(--muted);font-size:13px;line-height:1.45;margin:18px 0 0;text-align:left}
.note svg{flex:none;margin-top:2px;color:var(--brand)}
footer{position:relative;z-index:1;text-align:center;color:var(--muted);font-size:12px;line-height:1.7;padding:0 4px}
footer a{color:inherit;display:inline-block;padding:4px 2px}
@media (max-height:680px){body{padding-top:max(12px,env(safe-area-inset-top))}main{padding:0 0 12px}.card{padding-top:24px;padding-bottom:22px}.card .wm{height:44px;margin-bottom:14px}.lead{margin-bottom:16px}.note{margin-top:14px}}
@media (prefers-reduced-motion:reduce){.btn{transition:none}}
"""


def landing(message: str = "", button_href: str = "/auth/login?go=1", button_text: str = "Continuar con Google", status=200):
    msg = f'<p class="msg" role="status">{message}</p>' if message else ""
    html = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="color-scheme" content="light dark">
<meta name="robots" content="noindex,nofollow"><title>Runch</title>
<link rel="manifest" href="/manifest.webmanifest"><link rel="apple-touch-icon" href="/apple-touch-icon.png?v=2">
<meta name="theme-color" content="#F6F4EE" media="(prefers-color-scheme: light)"><meta name="theme-color" content="#0E0E0F" media="(prefers-color-scheme: dark)">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-title" content="Runch">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<link rel="icon" href="/icons/icon-192-v2.png" type="image/png">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Google+Sans+Flex:wght@400..600&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body>{BG}
<main>
 <section class="card">
  <div class="wm" role="img" aria-label="Runch">{LOGO}</div>
  <h1>Tu salud, <em>clara y a tu medida</em></h1>
  <p class="lead">El sueño, el corazón y los entrenos de tu reloj en un solo sitio, con un plan que se adapta a ti cada semana.</p>
  {msg}<a class="btn" href="{button_href}">{G_LOGO}<span>{button_text}</span></a>
  <p class="note"><svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 1 3 5v6c0 5.5 3.8 10.7 9 12 5.2-1.3 9-6.5 9-12V5l-9-4zm0 6a3 3 0 0 1 3 3v1h1v6H8v-6h1v-1a3 3 0 0 1 3-3zm0 2a1 1 0 0 0-1 1v1h2v-1a1 1 0 0 0-1-1z"/></svg>
  <span>Solo con invitación. Cada persona ve únicamente sus datos.</span></p>
 </section>
</main>
<footer>Datos de Garmin o Google Health · No es consejo médico<br><a href="/auth/privacidad">Privacidad</a> · <a href="/auth/condiciones">Condiciones</a></footer></body></html>"""
    return _resp(status, html)


def page(title, text, button=""):
    """Compatibilidad: mensajes con el diseño de la portada."""
    return landing(f"<b>{title}.</b> {text}")


# ------------------------------------------------------------------ páginas legales (públicas, sin sesión)
# Sin emails personales: el contacto público es la cuenta de Instagram de la app.
LEGAL_UPDATED = "10 de noviembre de 2026"
GOOGLE_SITE_FILES = {"google91ccfe2d5b372e65.html"}  # el archivo que da Search Console (URL-prefix de la web)

PRIVACY = """
<h1>Política de privacidad</h1>
<p class="upd">Última actualización: {updated}</p>
<p>Runch es una app privada, gratuita y solo con invitación que muestra tus datos de Garmin o de Google Health y te da
consejos y un plan de entreno con ayuda de IA. Esta página explica qué datos usa, para qué y qué puedes hacer con ellos.</p>

<h2>Responsable y contacto</h2>
<p>La app la gestiona su administrador. Para cualquier duda o para ejercer tus derechos, escríbenos por
mensaje directo en Instagram a <a href="https://www.instagram.com/runch.run/">@runch.run</a>.</p>

<h2>Qué datos usamos</h2>
<ul>
<li><b>Tu cuenta de Google:</b> solo tu nombre y tu email, para iniciar sesión y comprobar que tienes invitación.
No accedemos a tu Gmail, tus contactos, tu Drive ni nada más de tu cuenta.</li>
<li><b>Tus datos de Google Health</b> (solo si lo conectas en lugar de Garmin): entrenos, pasos, distancia, calorías,
minutos en zona activa, pulso (en reposo y a lo largo del día), HRV, VO2max, sueño y peso. Solo lectura: Runch no
escribe ni borra nada en tu cuenta de Google Health y no pide tu ubicación GPS. El permiso se guarda cifrado.</li>
<li><b>Tus datos de Garmin Connect:</b> sueño, pulso, HRV, estrés, Body Battery, pasos, actividades (con su ruta GPS),
series de fuerza, peso y datos parecidos, leídos con tu clave personal de la API de Garmin. La clave se guarda cifrada.</li>
<li><b>Lo que escribes en la app:</b> cómo te encuentras, molestias o lesiones, objetivos, disponibilidad, comidas,
preferencias del menú y lo que preguntas al chat.</li>
<li><b>Fotos de comida:</b> si usas esta función, la foto se analiza al momento y se descarta. Solo se guardan los
alimentos y cantidades estimados.</li>
<li><b>Tiempo:</b> la población que indiques para la previsión del tiempo.</li>
<li><b>Avisos:</b> si los activas, la suscripción de tu navegador para poder enviarte notificaciones.</li>
</ul>

<h2>Para qué</h2>
<p>Solo para enseñarte tus datos, calcular tendencias, escribir tus consejos, crear y ajustar tu plan y enviarte los
avisos que actives. No hay publicidad, no vendemos ni cedemos datos y no usamos analítica ni rastreadores.
Cada persona ve únicamente sus propios datos.</p>

<h2>Quién nos ayuda a prestar el servicio</h2>
<ul>
<li><b>Amazon Web Services</b>: alojamiento y almacenamiento, en la Unión Europea (Irlanda).</li>
<li><b>Anthropic</b> (IA Claude): recibe el resumen de tus datos necesario para escribir consejos, responder al chat,
crear el plan y analizar fotos de comida. Según sus condiciones para empresas, no usa estos datos para entrenar sus modelos.</li>
<li><b>Google</b>: inicio de sesión y tipografía de esta página; y Google Health, si lo eliges como origen de tus datos.</li>
<li><b>Garmin</b>: origen de tus datos de actividad y salud, si usas un reloj Garmin.</li>
<li><b>Open-Meteo</b>: previsión del tiempo (solo recibe la población o sus coordenadas).</li>
<li><b>El servicio de avisos de tu navegador</b> (Google, Apple o Mozilla), si activas las notificaciones.</li>
</ul>

<h2>Datos de Google Health</h2>
<p>El uso y la transferencia a cualquier otra app de la información recibida de las API de Google se ajustará a la
<a href="https://developers.google.com/terms/api-services-user-data-policy">Política de Datos de Usuario de los Servicios
de API de Google</a>, incluidos los requisitos de Uso Limitado. En concreto: solo usamos estos datos para mostrarte tus
datos, tus consejos y tu plan dentro de la app; no los usamos para publicidad, no los vendemos, no los usa ninguna
persona salvo que tú lo pidas (por ejemplo, para ayudarte con un problema) y no se usan para entrenar modelos de IA.
Solo se envían a los proveedores de arriba en la medida necesaria para darte el servicio.
Puedes retirar el permiso cuando quieras desde la app (Desconectar Google Health) o desde
<a href="https://myaccount.google.com/permissions">myaccount.google.com/permissions</a>.</p>

<h2>Cookies</h2>
<p>Solo usamos una cookie técnica de sesión (<code>gs_session</code>) para mantenerte dentro durante 30 días, y otras
temporales (unos minutos) mientras inicias sesión o conectas Google Health. No hay cookies de publicidad ni de terceros.</p>

<h2>Cuánto tiempo los guardamos</h2>
<p>Mientras tengas cuenta. Si la borras (menú de la app → <b>Borrar mi cuenta</b>) o nos lo pides, se borran
tus datos, tu clave de Garmin y tu permiso de Google Health (que además se retira en Google). Si solo desconectas
Google Health, se retira el permiso y puedes elegir borrar también los datos descargados.</p>

<h2>Tus derechos</h2>
<p>Puedes pedir acceso, corrección, borrado o una copia de tus datos, y oponerte a su uso, escribiéndonos a
<a href="https://www.instagram.com/runch.run/">@runch.run</a> en Instagram. También puedes reclamar ante la Agencia Española de Protección de Datos
(<a href="https://www.aepd.es">aepd.es</a>).</p>

<h2>Importante</h2>
<p>Runch no es un producto sanitario y no sustituye el consejo de un profesional de la salud.</p>
"""

TERMS = """
<h1>Condiciones del servicio</h1>
<p class="upd">Última actualización: {updated}</p>

<h2>El servicio</h2>
<p>Runch es una app privada y gratuita, solo con invitación y en fase beta. Puede cambiar, fallar o dejar de estar
disponible en cualquier momento.</p>

<h2>No es consejo médico</h2>
<p>Los datos, consejos y planes de entreno son orientativos y en parte los escribe una IA que puede equivocarse.
No sustituyen a un médico, fisioterapeuta ni entrenador. Escucha a tu cuerpo: entrenas bajo tu responsabilidad.</p>

<h2>Tu cuenta</h2>
<ul>
<li>Necesitas una cuenta de Google con invitación y, para tus datos, tu propia clave de la API de Garmin (que debes cuidar
como una contraseña) o tu cuenta de Google Health.</li>
<li>El acceso es personal: no lo compartas ni intentes ver datos de otras personas.</li>
<li>El uso de la IA tiene un tope mensual; al llegar a él, los textos de IA vuelven el mes siguiente.</li>
<li>Puedes borrar tu cuenta y tus datos cuando quieras desde el menú de la app.</li>
</ul>

<h2>Invitaciones</h2>
<p>El administrador puede retirar una invitación o cerrar el servicio. Si lo cierra, borrará los datos.</p>

<h2>Responsabilidad</h2>
<p>El servicio se ofrece tal cual, sin garantías. En la medida en que lo permita la ley, no nos hacemos responsables de
daños derivados de su uso, de errores en los datos o de que no esté disponible.</p>

<h2>Marcas</h2>
<p>Garmin y Garmin Connect son marcas de Garmin Ltd. Google y Google Health son marcas de Google LLC.
Runch no está afiliada a Garmin, Google ni Anthropic.</p>

<h2>Cambios y ley aplicable</h2>
<p>Si cambian estas condiciones, lo avisaremos en la app. Se rigen por la ley española.
Dudas: <a href="https://www.instagram.com/runch.run/">@runch.run</a> en Instagram. Ver también la <a href="/auth/privacidad">política de privacidad</a>.</p>
"""

LEGAL_CSS = BASE_CSS + """
body{padding:env(safe-area-inset-top) env(safe-area-inset-right) env(safe-area-inset-bottom) env(safe-area-inset-left);overflow-x:hidden}
.bg{position:absolute;inset:0 0 auto;height:calc(var(--h)*3.2);--h:clamp(64px,10vw,104px);justify-content:flex-start;padding-top:calc(var(--h)*.2);
 -webkit-mask:radial-gradient(75% 100% at 100% 0,#000 25%,transparent);mask:radial-gradient(75% 100% at 100% 0,#000 25%,transparent)}
header{position:relative;z-index:1;max-width:760px;margin:0 auto;padding:22px 20px 0}
header a{display:inline-flex;border-radius:8px}header .wm{height:32px}
main{position:relative;z-index:1;max-width:760px;margin:18px auto 28px;padding:32px 36px;background:var(--card);border:1px solid var(--line);
 border-radius:32px;box-shadow:var(--shadow);overflow-wrap:break-word}
@media (max-width:820px){main{margin:16px 12px 24px;padding:24px 20px;border-radius:26px}}
h1{font-size:clamp(26px,6vw,32px);line-height:1.15;font-weight:500;letter-spacing:-.02em;margin:0 0 6px;text-wrap:balance}
h2{font-size:18px;line-height:1.3;font-weight:600;margin:30px 0 6px;color:var(--brand)}
p{margin:0 0 12px}.upd{color:var(--muted);font-size:14px}ul{padding-left:20px;margin:0 0 12px}li{margin:6px 0}
code{font-size:14px;background:var(--note);border-radius:6px;padding:1px 6px}
footer{position:relative;z-index:1;text-align:center;color:var(--muted);font-size:13px;padding:0 16px 28px}
footer a{color:inherit;display:inline-block;padding:4px 2px}
"""


def legal(kind: str):
    body = (PRIVACY if kind == "privacidad" else TERMS).format(updated=LEGAL_UPDATED)
    title = "Política de privacidad" if kind == "privacidad" else "Condiciones del servicio"
    doc = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#F6F4EE" media="(prefers-color-scheme: light)"><meta name="theme-color" content="#0E0E0F" media="(prefers-color-scheme: dark)">
<title>{title} · Runch</title><link rel="icon" href="/icons/icon-192-v2.png" type="image/png">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Google+Sans+Flex:wght@400..600&display=swap" rel="stylesheet">
<style>{LEGAL_CSS}</style></head><body>{BG}
<header><a href="/auth/login" aria-label="Runch, inicio"><span class="wm">{LOGO}</span></a></header>
<main>{body}</main>
<footer><a href="/auth/login">Inicio</a> · <a href="/auth/privacidad">Privacidad</a> · <a href="/auth/condiciones">Condiciones</a></footer>
</body></html>"""
    return _resp(200, doc)


def handler(event, _ctx):
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    if not hmac.compare_digest(headers.get("x-origin-verify", ""), ORIGIN_SECRET):
        return _resp(403, "Prohibido", ctype="text/plain")
    host = headers.get("x-forwarded-host") or headers.get("host")
    host = headers.get("x-viewer-host", host)
    base = f"https://{host}"
    path = event.get("rawPath", "")
    qs = event.get("queryStringParameters") or {}
    cookies = dict(c.split("=", 1) for c in event.get("cookies") or [] if "=" in c)
    g = _google()

    # Verificación de propiedad en Google Search Console (método "archivo HTML"). Solo el nombre exacto que da Google:
    # Google prueba también un nombre inventado y, si la web responde 200 a cualquiera, la marca como pirateada.
    if path[1:] in GOOGLE_SITE_FILES:
        return _resp(200, f"google-site-verification: {path[1:]}", ctype="text/html; charset=utf-8")
    if path in ("/auth/privacidad", "/auth/condiciones"):
        return legal(path.rsplit("/", 1)[1])
    if path == "/auth/logout":
        return _resp(302, headers={"location": "/auth/login?out=1"},
                     cookies=["gs_session=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax"])

    if path == "/auth/login":
        if g is None:
            return landing("El acceso con Google aún no está configurado.")
        if "out" in qs:
            return landing("Has cerrado la sesión.")
        if "go" not in qs:
            nxt = qs.get("next", "/")
            return landing(button_href="/auth/login?go=1&next=" + urllib.parse.quote(nxt, safe=""))
        verifier = _b64(secrets.token_bytes(32))
        state = _b64(secrets.token_bytes(16))
        nxt = qs.get("next", "/")
        if not nxt.startswith("/") or nxt.startswith("//"):
            nxt = "/"
        params = {
            "client_id": g["id"], "redirect_uri": f"{base}/auth/callback", "response_type": "code",
            "scope": "openid email profile", "state": state, "prompt": "select_account",
            "code_challenge": _b64(hashlib.sha256(verifier.encode()).digest()), "code_challenge_method": "S256",
        }
        tmp = json.dumps({"v": verifier, "s": state, "n": nxt})
        return _resp(302, headers={"location": "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)},
                     cookies=[f"gs_oauth={_b64(tmp.encode())}; Path=/auth; Max-Age=600; Secure; HttpOnly; SameSite=Lax"])

    if path == "/auth/callback":
        try:
            tmp = json.loads(base64.urlsafe_b64decode(cookies["gs_oauth"] + "=="))
        except Exception:
            return _resp(302, headers={"location": "/auth/login?go=1"})
        if g is None or qs.get("state") != tmp["s"] or "code" not in qs:
            return landing("No se pudo completar el acceso. Vuelve a intentarlo.")
        data = urllib.parse.urlencode({
            "code": qs["code"], "client_id": g["id"], "client_secret": g["secret"], "code_verifier": tmp["v"],
            "redirect_uri": f"{base}/auth/callback", "grant_type": "authorization_code",
        }).encode()
        try:
            with urllib.request.urlopen("https://oauth2.googleapis.com/token", data=data, timeout=10) as r:
                tok = json.load(r)
            claims = json.loads(base64.urlsafe_b64decode(tok["id_token"].split(".")[1] + "=="))
        except Exception:
            return landing("Google no ha aceptado el acceso. Vuelve a intentarlo.")
        email = str(claims.get("email", "")).lower()
        ok = (claims.get("iss") in ("https://accounts.google.com", "accounts.google.com")
              and claims.get("aud") == g["id"] and int(claims.get("exp", 0)) > time.time()
              and claims.get("email_verified") is True)
        if ok:
            try:
                ok = _check_user(email, str(claims.get("given_name") or claims.get("name") or "")[:60])
            except Exception:  # noqa: BLE001
                return landing("No se pudo comprobar tu acceso. Vuelve a intentarlo en un momento.")
        if not ok:
            return landing(f"La cuenta <b>{html.escape(email) or 'elegida'}</b> no tiene invitación. Pide a quien te pasó el enlace que te invite con este email.",
                           button_text="Probar con otra cuenta")
        return _resp(302, headers={"location": tmp["n"]}, cookies=[
            f"gs_session={session_cookie(email)}; Path=/; Max-Age={SESSION_DAYS * 86400}; Secure; HttpOnly; SameSite=Lax",
            "gs_oauth=; Path=/auth; Max-Age=0; Secure; HttpOnly; SameSite=Lax",
        ])

    return _resp(404, "No encontrado", ctype="text/plain")
