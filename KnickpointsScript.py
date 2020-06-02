# -*- coding: cp1252 -*-
# ---------------------------------------------------------------------------
# KnickpointPython.py
# Created on: 16/10/2012
# Author: Gustavo Lopes Queiroz
# Contact: gustavo.lopes.queiroz@gmail.com
# Special thanks to: Edenilson Nascimento, the code's co-author; and Eduardo
# Salamuni, Ph.D., Professor and research coordinator.
# ---------------------------------------------------------------------------

# Import modules
import sys, string, os, arcgisscripting, tempfile, math

class LicenseError(Exception):
    pass

# Geoprocessor object
gp = arcgisscripting.create()

PastaGIS = gp.GetInstallInfo("desktop")["InstallDir"]
# Load toolboxes
gp.AddToolbox(PastaGIS + "/ArcToolbox/Toolboxes/Spatial Analyst Tools.tbx")
gp.AddToolbox(PastaGIS + "/ArcToolbox/Toolboxes/Conversion Tools.tbx")
gp.AddToolbox(PastaGIS + "/ArcToolbox/Toolboxes/Data Management Tools.tbx")

# Digital Elevation Model and other input
GridEntrada = gp.GetParameterAsText(0)
GridCellSizeX = gp.GetRasterProperties_management(GridEntrada, "CELLSIZEX")
GridCellSizeY = gp.GetRasterProperties_management(GridEntrada, "CELLSIZEY")
ConValor = long( gp.GetParameterAsText(1) )/ ( 100 * ( ( ( GridCellSizeX + GridCellSizeY ) / 2 ) / 30 ) )

EntradaDesc = gp.Describe(GridEntrada)
EntradaSpacRef = EntradaDesc.SpatialReference

# Temporary folder
dirtemp = gp.GetParameterAsText(3) + "//KnickpointFinderTemp"
if not os.path.exists(dirtemp):
    os.makedirs(dirtemp)

# Allow overwrite
gp.overwriteOutput = True

try:

    if gp.CheckExtension("spatial") == "Available":
        gp.CheckOutExtension("spatial")
    else:
        raise LicenseError
    if gp.CheckExtension("3D") == "Available":
        gp.CheckOutExtension("3D")
    else:
        raise LicenseError

    if os.path.exists(dirtemp + "\\Merge"):
        txtfile = open(dirtemp + "\\Merge", 'r')
        readcon = txtfile.readline().replace("\n","")
        readnam = txtfile.readline().replace("\n","")
        txtfile.close()
    else:
        readcon = -1
        readnam = ""

    if readcon != str(ConValor) or readnam != GridEntrada:
        # Generate Drainage Network
        gp.SetProgressor("step", "Generate drainage network...")
        StrErro = "Drainage network generation failed."

        gp.SetProgressorPosition(0)
        gp.AddMessage("Processing Fill...")
        SaidaFill = dirtemp + "//DrenFill.tif"
        gp.Fill_sa(GridEntrada, SaidaFill, "")

        gp.SetProgressorPosition(10)
        gp.AddMessage("Processing Flow Direction...")
        SaidaFlowDir = dirtemp + "//DrenFlowDir"
        DropRaster = ""
        gp.FlowDirection_sa(SaidaFill, SaidaFlowDir, "NORMAL", DropRaster)

        gp.SetProgressorPosition(20)
        gp.AddMessage("Processing Flow Accumulation...")
        SaidaFlowAcc = dirtemp + "//DrenFlowAcc"
        gp.FlowAccumulation_sa(SaidaFlowDir, SaidaFlowAcc, "", "FLOAT")

        gp.SetProgressorPosition(30)
        gp.AddMessage("Processing Con...")
        gp.AddMessage(str(ConValor))
        SaidaCon = dirtemp + "//DrenCon"
        gp.Con_sa(SaidaFlowAcc, "1", SaidaCon, "", "Value > " + str(int(ConValor)))

        gp.SetProgressorPosition(40)
        gp.AddMessage("Processing Stream Order...")
        SaidaStreamO = dirtemp + "//DrenStreamO"
        gp.StreamOrder_sa(SaidaCon, SaidaFlowDir, SaidaStreamO, "STRAHLER")

        gp.SetProgressorPosition(50)
        gp.AddMessage("Processing Stream to Feature...")
        DrenShape = dirtemp + "//DrenShape.shp"
        gp.StreamToFeature_sa(SaidaStreamO, SaidaFlowDir, DrenShape, "NO_SIMPLIFY")

        NomeGDB = dirtemp + "\\TempGDB.gdb"
        if not os.path.exists(NomeGDB):
            gp.SetProgressorPosition(60)
            gp.AddMessage("Processing Create File GDB...")
            gp.CreateFileGDB_management(dirtemp, "TempGDB")

        gp.SetProgressorPosition(70)
        gp.AddMessage("Processing Feature Class to Feature Class...")
        DrenGDB= dirtemp + "\\TempGDB.gdb\\DrenagemGDBFC"
        gp.FeatureClassToFeatureClass_conversion(DrenShape, NomeGDB, "DrenagemGDBFC")

        gp.SetProgressorPosition(80)
        gp.AddMessage("Processing Make Feature Layer...")
        NomeDrenLayer = "Drenagem Automatizada Con " + str(ConValor)
        gp.MakeFeatureLayer_management(DrenGDB, NomeDrenLayer)

        # River Merge
        # Count the highest stream order
        GridCodeList = []
        rows = gp.SearchCursor(NomeDrenLayer)
        row = rows.Next()

        while row:
            GridCodeList.append(row.getValue("GRID_CODE"))
            row = rows.Next()
        GridCodeList.sort()

        MaxGridCode = GridCodeList[-1]
        del row
        del rows
        del GridCodeList

        GridCodeAtual = MaxGridCode

        gp.SetProgressor("default", "Processing River Merge...")
        gp.AddMessage("Merging drainage segments. This might be lengthy...")
        StrErro = "River merging failed."
        # Dissolve by MERGEID
        # Insert new fields in the attribute table
        gp.AddField_management(NomeDrenLayer, "MERGEID", "LONG")

        gp.AddField_management(NomeDrenLayer, "OID_LINK", "LONG")

        gp.AddField_management(NomeDrenLayer, "LINK_OK", "SHORT")

        CursorField = gp.UpdateCursor(NomeDrenLayer)
        LinhaField = CursorField.Next()

        while LinhaField:
            LinhaField.MERGEID = -1
            LinhaField.OID_LINK = -1
            LinhaField.LINK_OK = 0
            CursorField.UpdateRow(LinhaField)
            LinhaField = CursorField.Next()

        del CursorField, LinhaField

        def ComprimentoComposto(PointerLinha):
            ComprimentoTotal = 0
            NumLinhas = 1
            ContinuarSomando = True
            LinhaAtual = PointerLinha
            while ContinuarSomando == True:
                ComprimentoTotal += LinhaAtual.Shape_Length
                if LinhaAtual.OID_LINK == -1:
                    ContinuarSomando = False
                else:
                    CursorProx = gp.SearchCursor(NomeDrenLayer, "OBJECTID = " + str(LinhaAtual.OID_LINK))
                    LinhaProx = CursorProx.Next()
                    while LinhaProx:
                        LinhaAtual = LinhaProx
                        NumLinhas += 1
                        break
                    del CursorProx, LinhaProx

            return ComprimentoTotal

        # Begin River Merge
        GridCodeAtual = 1

        # Number of union (merge) groups ready for Dissolve
        MergeIDCount = 0

        ContinuarRodando = True

        while ContinuarRodando == True:
            CursorFoco = gp.UpdateCursor(NomeDrenLayer)
            LinhaFoco = CursorFoco.Next()

            ContinuarRodando = False

            while LinhaFoco:
                EmEspera = False
                if LinhaFoco.LINK_OK == 0:
                    if LinhaFoco.OID_LINK == -1:
                        CursorSec = gp.SearchCursor(NomeDrenLayer, "TO_NODE = " + str(LinhaFoco.FROM_NODE))
                        LinhaSec = CursorSec.Next()
                        while LinhaSec:
                            ContinuarRodando = True # There are more operations to do after the loop ends 'Keep running'
                            EmEspera = True
                            break
                        del CursorSec, LinhaSec
                    if EmEspera == False:
                        if LinhaFoco.MERGEID == -1:
                            LinhaFoco.MERGEID = MergeIDCount
                            CursorFoco.UpdateRow(LinhaFoco)
                            MergeIDCount += 1

                        # Search if there is a line with Tonode == FocusLine.Tonode
                        ToNodeMaior = True
                        CursorSec = gp.SearchCursor(NomeDrenLayer, "TO_NODE = " + str(LinhaFoco.TO_NODE) + " and OBJECTID <> " + str(LinhaFoco.OBJECTID))
                        LinhaSec = CursorSec.Next()
                        while LinhaSec:
                            if LinhaSec.OID_LINK == -1:
                                CursorTerc = gp.SearchCursor(NomeDrenLayer, "TO_NODE = " + str(LinhaSec.FROM_NODE))
                                LinhaTerc = CursorTerc.Next()
                                while LinhaTerc:
                                    EmEspera = True
                                    ContinuarRodando = True # There are more operations to do after the loop ends 'Keep running'
                                    break
                                del CursorTerc, LinhaTerc
                                if EmEspera == True:
                                    break
                            if ComprimentoComposto(LinhaFoco) < ComprimentoComposto(LinhaSec):
                                ToNodeMaior = False
                                break
                            LinhaSec = CursorSec.Next()
                        del CursorSec, LinhaSec
                        if EmEspera == False:
                            # Find and mark the next line downstream joining it with the FocusLine
                            if ToNodeMaior == True:
                                CursorSec = gp.UpdateCursor(NomeDrenLayer, "FROM_NODE = " + str(LinhaFoco.TO_NODE))
                                LinhaSec = CursorSec.Next()
                                while LinhaSec:
                                    LinhaSec.MERGEID = LinhaFoco.MERGEID
                                    LinhaSec.OID_LINK = LinhaFoco.OBJECTID
                                    CursorSec.UpdateRow(LinhaSec)
                                    break
                                del CursorSec, LinhaSec
                            LinhaFoco.LINK_OK = 1
                            CursorFoco.UpdateRow(LinhaFoco)
                LinhaFoco = CursorFoco.Next()
            del CursorFoco, LinhaFoco
        DrenDissolve = NomeGDB + "\\DrenDissolve"
        gp.Dissolve_management(NomeDrenLayer,DrenDissolve, "MERGEID")

        # 3D drainage network
        gp.SetProgressor("default", "Processing Interpolate Shape...")
        NomeDren3D = dirtemp + "\\TempGDB.gdb\\Dren3D"
        gp.interpolateshape_3d( GridEntrada, DrenDissolve, NomeDren3D )

        txtfile = open(dirtemp + "\\Merge", 'w')
        txtfile.write(str(ConValor) + "\n" + GridEntrada)
        txtfile.close()

        gp.AddMessage("The 3D drainage network was generated successfully.")
    else:
        gp.SetProgressor("default", "Loading data...")
        StrErro = "It wasn't possible to load the existing 3D drainage network."
        DrenGDB= dirtemp + "\\TempGDB.gdb\\DrenagemGDBFC"
        gp.AddMessage("A 3D drainage network with these parameters already exists and will be used...")
        NomeDrenLayer = "Drenagem Automatizada Con " + str(ConValor)
        NomeDren3D = dirtemp + "\\TempGDB.gdb\\Dren3D"
        gp.MakeFeatureLayer_management(DrenGDB, NomeDrenLayer)

    # Save the 3D drainage network file
    if gp.GetParameterAsText(5) == "true":
        gp.FeatureclassToFeatureclass_conversion( NomeDren3D, gp.GetParameterAsText(3), gp.GetParameterAsText(6) + ".shp" )

    # Identify geometry field
    DescLayer = gp.Describe(NomeDren3D)
    CampoGeometria = DescLayer.ShapeFieldName

    def Comprimento(LinhaPointer):
        Feature = LinhaPointer.GetValue(CampoGeometria)
        return Feature.Length


    gp.SetProgressor("default", "Processing RDE...")
    StrErro = "RDE index measuring failed."

    gp.SetProgressorPosition(0)
    gp.AddMessage("Creating point layer...")
    ReferenciaEspacial = gp.CreateSpatialReference_management("", NomeDren3D, "", "", "", "", "0")
    NomePontos = gp.GetParameterAsText(3) + "\\" + gp.GetParameterAsText(4) + ".shp"
    gp.CreateFeatureclass_management(gp.GetParameterAsText(3), gp.GetParameterAsText(4), "POINT", "", "DISABLED", "DISABLED", ReferenciaEspacial)
    gp.AddField_management(NomePontos, "RDEt", "DOUBLE")
    gp.AddField_management(NomePontos, "RDEs", "DOUBLE")
    gp.AddField_management(NomePontos, "RDEsRDEt", "DOUBLE")
    gp.AddField_management(NomePontos, "OrdemAnom", "SHORT")

    def ObterListPont(Linha):
        Feature = Linha.GetValue(CampoGeometria)
        ListaPontos = []
        ParteNum = 0
        ParteTotal = Feature.PartCount
        # Loop for each part of the feature
        while ParteNum < ParteTotal:
            Parte = Feature.GetPart(ParteNum)
            Vertice = Parte.Next()
            while Vertice:
                if Vertice:
                    # Add the coordinates of each vertex to the points list
                    ListaPontos.append([Vertice.X,Vertice.Y,Vertice.Z])
                Vertice = Parte.Next()

            ParteNum += 1
        return ListaPontos

    def Dist(x1,y1,x2,y2):
        return math.sqrt(math.pow(math.fabs(x1-x2),2)+math.pow(math.fabs(y1-y2),2))

    ConstEquidistAltimetrica = int(gp.GetParameterAsText(2)) # Contour interval
    RDEs = 0
    RDEt = 0
    XAtual = 0
    YAtual = 0
    XAnterior = 0
    YAnterior = 0
    XSegmento = 0
    YSegmento = 0
    CompSegmento = 0

    gp.AddMessage("Calculating RDE indexes...") # Knickpoint Finder

    CursorRDE = gp.SearchCursor(NomeDren3D)
    LinhaRDE = CursorRDE.Next()

    while LinhaRDE:
        ListVert = ObterListPont(LinhaRDE)

        # Calculate RDEt -> RDEt = altimetric distance between the two ends / ln( river length )
        RDEt = (ListVert[0][2] - ListVert[-1][2]) / max(0.0001, math.log( Comprimento(LinhaRDE) ) )
        XAtual = ListVert[0][0]
        YAtual = ListVert[0][1]
        XAnterior = ListVert[0][0]
        YAnterior = ListVert[0][1]
        XSegmento = ListVert[0][0]
        YSegmento = ListVert[0][1]
        PontoX = -1
        PontoY = -1
        CompSegmento = 0
        ExtNascente = 0

        ValorPixelMontante = ListVert[0][2]

        v = 0
        while v < len(ListVert):
            if RDEt < 1:
                break
            if ValorPixelMontante - ListVert[v][2] >= ConstEquidistAltimetrica/2 and PontoX == -1 and PontoY == -1:
                PontoX = ListVert[v][0]
                PontoY = ListVert[v][1]
            if ValorPixelMontante - ListVert[v][2] >= ConstEquidistAltimetrica:
                # Measure RDEs
                RDEs = ((ValorPixelMontante - ListVert[v][2]) / (CompSegmento)) * (ExtNascente)
                # Check if there is an anomaly
                if RDEs / max(0.0001, RDEt) >= 2:
                    # Create anomaly point
                    CursorPontos = gp.InsertCursor(NomePontos)
                    LinhaPonto = CursorPontos.NewRow()
                    Ponto = gp.CreateObject("Point")
                    Ponto.X = PontoX
                    Ponto.Y = PontoY
                    LinhaPonto.Shape = Ponto
                    LinhaPonto.RDEs = RDEs
                    LinhaPonto.RDEt = RDEt
                    LinhaPonto.RDEsRDEt = RDEs/max(0.0001,RDEt)
                    if RDEs / max(0.0001, RDEt) >= 2:
                        if RDEs / max(0.0001, RDEt) >= 10:
                            LinhaPonto.OrdemAnom = 1
                        else:
                            LinhaPonto.OrdemAnom = 2
                    CursorPontos.InsertRow(LinhaPonto)

                    del CursorPontos, LinhaPonto
                ValorPixelMontante = ListVert[v][2]
                CompSegmento = 0
                PontoX = -1
                PontoY = -1
            v += 1
            if v == len(ListVert) - 1:
                break
            else:
                CompSegmento += Dist(ListVert[v][0],ListVert[v][1],ListVert[v-1][0],ListVert[v-1][1])
                ExtNascente += Dist(ListVert[v][0],ListVert[v][1],ListVert[v-1][0],ListVert[v-1][1])
        LinhaRDE = CursorRDE.Next()

    # OUTPUT
    gp.MakeFeatureLayer_management(gp.GetParameterAsText(3) + "\\" + gp.GetParameterAsText(4) + ".shp", gp.GetParameterAsText(4))
    gp.SetParameterAsText(7,gp.GetParameterAsText(3) + "\\" + gp.GetParameterAsText(4) + ".shp")

    if gp.GetParameterAsText(5) == "true":
        gp.MakeFeatureLayer_management(gp.GetParameterAsText(3) + "\\" + gp.GetParameterAsText(6) + ".shp", gp.GetParameterAsText(6))
        gp.SetParameterAsText(8,gp.GetParameterAsText(3) + "\\" + gp.GetParameterAsText(6) + ".shp")

    gp.AddMessage("Knickpoint Finder was successful.")

    # Delete temporary folder
    gp.delete_management(dirtemp, "")
except LicenseError:
    gp.AddMessage("Spatial Analyst or 3D Analyst licenses not available. Make sure licenses are checked in Customize > Extensions...")
except:
    e = sys.exc_info()[1]
    gp.AddMessage(e.args[0])
    gp.AddError("Error! " + StrErro)
