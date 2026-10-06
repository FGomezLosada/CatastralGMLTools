<?xml version="1.0" encoding="ISO-8859-1"?>
<!-- Fichero de prueba SINTÉTICO de Catastral GML Tools: edificio en dos partes y una piscina (año ficticio, coordenadas inventadas). -->
<gml:FeatureCollection gml:id="ES.LOCAL.BU" xmlns:base="urn:x-inspire:specification:gmlas:BaseTypes:3.2" xmlns:bu-core2d="http://inspire.jrc.ec.europa.eu/schemas/bu-core2d/2.0" xmlns:bu-ext2d="http://inspire.jrc.ec.europa.eu/schemas/bu-ext2d/2.0" xmlns:gml="http://www.opengis.net/gml/3.2" xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://inspire.jrc.ec.europa.eu/schemas/bu-ext2d/2.0 http://inspire.ec.europa.eu/draft-schemas/bu-ext2d/2.0/BuildingExtended2D.xsd">
<gml:featureMember>
<bu-ext2d:Building gml:id="ES.LOCAL.BU.Edificio_1">
<bu-core2d:beginLifespanVersion>2026-10-06T00:00:00</bu-core2d:beginLifespanVersion>
<bu-core2d:conditionOfConstruction>functional</bu-core2d:conditionOfConstruction>
<bu-core2d:inspireId><base:Identifier><base:localId>Edificio_1</base:localId><base:namespace>ES.LOCAL.BU</base:namespace></base:Identifier></bu-core2d:inspireId>
<bu-ext2d:geometry><bu-core2d:BuildingGeometry><bu-core2d:geometry>
<gml:Surface gml:id="Surface_ES.LOCAL.BU.Edificio_1" srsName="urn:ogc:def:crs:EPSG::25830"><gml:patches>
<gml:PolygonPatch><gml:exterior><gml:LinearRing><gml:posList srsDimension="2" count="5">421502.00 4070502.00 421502.00 4070508.00 421510.00 4070508.00 421510.00 4070502.00 421502.00 4070502.00</gml:posList></gml:LinearRing></gml:exterior></gml:PolygonPatch>
<gml:PolygonPatch><gml:exterior><gml:LinearRing><gml:posList srsDimension="2" count="5">421512.00 4070502.00 421512.00 4070506.00 421516.00 4070506.00 421516.00 4070502.00 421512.00 4070502.00</gml:posList></gml:LinearRing></gml:exterior></gml:PolygonPatch>
</gml:patches></gml:Surface>
</bu-core2d:geometry>
<bu-core2d:horizontalGeometryEstimatedAccuracy uom="m">0.1</bu-core2d:horizontalGeometryEstimatedAccuracy>
<bu-core2d:horizontalGeometryReference>footPrint</bu-core2d:horizontalGeometryReference>
<bu-core2d:referenceGeometry>true</bu-core2d:referenceGeometry>
</bu-core2d:BuildingGeometry></bu-ext2d:geometry>
<bu-ext2d:numberOfFloorsAboveGround>2</bu-ext2d:numberOfFloorsAboveGround>
</bu-ext2d:Building>
</gml:featureMember>
<gml:featureMember>
<bu-ext2d:OtherConstruction gml:id="ES.LOCAL.BU.Edificio_1_PI.1">
<bu-core2d:beginLifespanVersion>2026-10-06T00:00:00</bu-core2d:beginLifespanVersion>
<bu-core2d:conditionOfConstruction xsi:nil="true" nilReason="other:unpopulated"></bu-core2d:conditionOfConstruction>
<bu-core2d:inspireId><base:Identifier><base:localId>Edificio_1_PI.1</base:localId><base:namespace>ES.LOCAL.BU</base:namespace></base:Identifier></bu-core2d:inspireId>
<bu-ext2d:constructionNature>openAirPool</bu-ext2d:constructionNature>
<bu-ext2d:geometry><gml:Polygon gml:id="Polygon_ES.LOCAL.BU.Edificio_1_PI.1" srsName="urn:ogc:def:crs:EPSG::25830"><gml:exterior><gml:LinearRing><gml:posList srsDimension="2" count="5">421502.00 4070512.00 421502.00 4070515.00 421508.00 4070515.00 421508.00 4070512.00 421502.00 4070512.00</gml:posList></gml:LinearRing></gml:exterior></gml:Polygon></bu-ext2d:geometry>
</bu-ext2d:OtherConstruction>
</gml:featureMember>
</gml:FeatureCollection>
