"""XML fixtures for EIS FTP parser tests."""

# Реалистичное извещение 44-ФЗ (электронный аукцион) в схеме ЕИС
# http://zakupki.gov.ru/oos/export/1 — структура повторяет реальные
# fcsNotificationEF из региональных выгрузок.
NOTIFICATION_44FZ_EF = """<?xml version="1.0" encoding="UTF-8"?>
<ns2:export xmlns="http://zakupki.gov.ru/oos/types/1"
            xmlns:ns2="http://zakupki.gov.ru/oos/export/1">
  <ns2:fcsNotificationEF schemeVersion="10.3">
    <id>123456789</id>
    <purchaseNumber>0152300011926000042</purchaseNumber>
    <docNumber>0152300011926000042-01</docNumber>
    <directDate>2026-07-14T09:15:00+03:00</directDate>
    <publishDTInEIS>2026-07-14T09:20:00+03:00</publishDTInEIS>
    <href>https://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html?regNumber=0152300011926000042</href>
    <purchaseObjectInfo>Выполнение работ по расчистке территории от аварийных деревьев в Советском округе г. Омска</purchaseObjectInfo>
    <purchaseResponsible>
      <responsibleOrg>
        <regNum>03521000123</regNum>
        <consRegistryNum>152300011</consRegistryNum>
        <fullName>АДМИНИСТРАЦИЯ СОВЕТСКОГО АДМИНИСТРАТИВНОГО ОКРУГА ГОРОДА ОМСКА</fullName>
        <INN>5501021880</INN>
        <KPP>550101001</KPP>
      </responsibleOrg>
      <responsibleRole>CU</responsibleRole>
    </purchaseResponsible>
    <placingWay>
      <code>EF</code>
      <name>Электронный аукцион</name>
    </placingWay>
    <procedureInfo>
      <collecting>
        <startDate>2026-07-14T09:20:00+03:00</startDate>
        <endDT>2026-07-22T08:00:00+03:00</endDT>
      </collecting>
      <bidding>
        <date>2026-07-23T10:00:00+03:00</date>
      </bidding>
    </procedureInfo>
    <lot>
      <maxPrice>1250000.00</maxPrice>
      <currency>
        <code>RUB</code>
        <name>Российский рубль</name>
      </currency>
      <applicationGuarantee>
        <amount>12500.00</amount>
        <part>1.0</part>
      </applicationGuarantee>
      <contractGuarantee>
        <amount>62500.00</amount>
        <part>5.0</part>
      </contractGuarantee>
      <purchaseObjects>
        <purchaseObject>
          <OKPD2>
            <code>81.30.10.131</code>
            <name>Услуги по обрезке деревьев и живых изгородей</name>
          </OKPD2>
          <name>Расчистка территории от аварийных деревьев</name>
          <price>1250000.00</price>
        </purchaseObject>
        <purchaseObject>
          <OKPD2>
            <code>43.12.11.100</code>
            <name>Работы по расчистке территорий</name>
          </OKPD2>
          <name>Планировка территории</name>
        </purchaseObject>
      </purchaseObjects>
    </lot>
  </ns2:fcsNotificationEF>
</ns2:export>
"""

# Извещение 223-ФЗ (purchaseNotice) в схеме
# http://zakupki.gov.ru/223fz/purchase/1
NOTICE_223FZ = """<?xml version="1.0" encoding="UTF-8"?>
<purchaseNotice xmlns="http://zakupki.gov.ru/223fz/purchase/1"
                xmlns:ns2="http://zakupki.gov.ru/223fz/types/1">
  <header>
    <guid>a1b2c3d4-e5f6-7890-abcd-ef1234567890</guid>
    <creationDateTime>2026-07-14T11:00:00+03:00</creationDateTime>
  </header>
  <body>
    <item>
      <guid>a1b2c3d4-e5f6-7890-abcd-ef1234567890</guid>
      <purchaseNoticeData>
        <registrationNumber>32615544332</registrationNumber>
        <name>Поставка печного топлива для нужд филиала в Новосибирской области</name>
        <purchaseMethodName>Запрос котировок в электронной форме</purchaseMethodName>
        <customer>
          <mainInfo>
            <fullName>АКЦИОНЕРНОЕ ОБЩЕСТВО "СИБИРСКИЕ КОММУНАЛЬНЫЕ СИСТЕМЫ"</fullName>
            <inn>5406012345</inn>
            <kpp>540601001</kpp>
          </mainInfo>
        </customer>
        <publicationDateTime>2026-07-14T11:05:00+03:00</publicationDateTime>
        <submissionCloseDateTime>2026-07-21T10:00:00+03:00</submissionCloseDateTime>
        <lots>
          <lot>
            <lotData>
              <lotNumber>1</lotNumber>
              <initialSum>4800000.00</initialSum>
              <currency>
                <code>RUB</code>
              </currency>
              <lotItems>
                <lotItem>
                  <okpd2>
                    <code>19.20.28.120</code>
                    <name>Топливо печное бытовое</name>
                  </okpd2>
                </lotItem>
              </lotItems>
            </lotData>
          </lot>
        </lots>
        <urlEIS>https://zakupki.gov.ru/223/purchase/public/purchase/info/common-info.html?regNumber=32615544332</urlEIS>
      </purchaseNoticeData>
    </item>
  </body>
</purchaseNotice>
"""

# Извещение 44-ФЗ, не проходящее фильтры (капремонт МКД — стоп-слово)
NOTIFICATION_44FZ_STOPWORD = NOTIFICATION_44FZ_EF.replace(
    "Выполнение работ по расчистке территории от аварийных деревьев в Советском округе г. Омска",
    "Капитальный ремонт многоквартирных домов по программе 2026 года",
).replace("0152300011926000042", "0152300011926000099")

# Протокол подведения итогов 44-ФЗ (fcsProtocolEF3)
PROTOCOL_44FZ = """<?xml version="1.0" encoding="UTF-8"?>
<ns2:export xmlns="http://zakupki.gov.ru/oos/types/1"
            xmlns:ns2="http://zakupki.gov.ru/oos/export/1">
  <ns2:fcsProtocolEF3 schemeVersion="10.3">
    <id>987654321</id>
    <purchaseNumber>0152300011926000042</purchaseNumber>
    <protocolNumber>0152300011926000042-3</protocolNumber>
    <publishDTInEIS>2026-07-24T14:30:00+03:00</publishDTInEIS>
    <abandonedReasonInfo/>
    <applications>
      <application>
        <journalNumber>1</journalNumber>
        <appRating>2</appRating>
        <price>1187500.00</price>
        <appParticipants>
          <appParticipant>
            <participantName>ООО "ЗЕЛЕНСТРОЙ"</participantName>
            <inn>5504098765</inn>
          </appParticipant>
        </appParticipants>
      </application>
      <application>
        <journalNumber>2</journalNumber>
        <appRating>1</appRating>
        <price>1062500.00</price>
        <appParticipants>
          <appParticipant>
            <participantName>ООО "ПОДРЯД ПРО"</participantName>
            <inn>5507112233</inn>
          </appParticipant>
        </appParticipants>
      </application>
      <application>
        <journalNumber>3</journalNumber>
        <appRating>3</appRating>
        <price>1200000.00</price>
        <appParticipants>
          <appParticipant>
            <participantName>ИП Сидоров А.А.</participantName>
            <inn>550700445566</inn>
          </appParticipant>
        </appParticipants>
      </application>
    </applications>
  </ns2:fcsProtocolEF3>
</ns2:export>
"""
