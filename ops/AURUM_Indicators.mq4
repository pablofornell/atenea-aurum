//+------------------------------------------------------------------+
//|                                           AURUM_Indicators.mq4   |
//|                         Aurum Kill Zones - Asia, London & NY      |
//|                                                                  |
//|  Marca visualmente las ventanas institucionales de Asia,          |
//|  Londres y NY con zonas de color, líneas y panel informativo.    |
//+------------------------------------------------------------------+
#property copyright   "Aurum"
#property link        ""
#property version     "1.02"
#property strict
#property indicator_chart_window

//--- Inputs Asia
input string   Separador0         = "=== SESIÓN ASIA ===";
input bool     MostrarAsia        = true;
input int      Asia_Inicio_H      = 0;   // Hora inicio Kill Zone Asia (UTC)
input int      Asia_Inicio_M      = 0;
input int      Asia_Fin_H         = 4;   // Hora fin Kill Zone Asia (UTC)
input int      Asia_Fin_M         = 0;
input color    ColorAsia          = C'180,255,180';  // Verde claro

//--- Inputs Londres
input string   Separador1         = "=== SESIÓN LONDRES ===";
input bool     MostrarLondres     = true;
input int      Londres_Inicio_H   = 7;   // Hora inicio Kill Zone Londres (UTC)
input int      Londres_Inicio_M   = 0;
input int      Londres_Fin_H      = 8;   // Hora fin Kill Zone Londres (UTC)
input int      Londres_Fin_M      = 30;
input color    ColorLondres       = C'173,216,255';  // Azul claro

//--- Inputs Nueva York
input string   Separador2         = "=== SESIÓN NUEVA YORK ===";
input bool     MostrarNY          = true;
input int      NY_Inicio_H        = 13;  // Hora inicio Kill Zone NY (UTC)
input int      NY_Inicio_M        = 30;
input int      NY_Fin_H           = 15;  // Hora fin Kill Zone NY (UTC)
input int      NY_Fin_M           = 0;
input color    ColorNY            = C'255,200,150';  // Naranja claro

//--- Líneas de apertura
input string   Separador3         = "=== LÍNEAS DE APERTURA ===";
input bool     LineaAperturaASIA  = true;
input bool     LineaAperturaLON   = true;
input bool     LineaAperturaNY    = true;
input color    ColorLineaASIA     = clrMediumSeaGreen;
input color    ColorLineaLON      = clrDodgerBlue;
input color    ColorLineaNY       = clrOrangeRed;
input int      GrosorLinea        = 1;   // FIX: was "GrosroLinea" (typo)
input ENUM_LINE_STYLE EstiloLinea = STYLE_DASH;

//--- Panel
input string   Separador4         = "=== PANEL ===";
input bool     MostrarPanel       = true;
input int      PanelX             = 15;
input int      PanelY             = 30;

//--- General
input int      DiasAtras          = 5;   // Cuántos días hacia atrás dibujar zonas

//--- Prefijo para objetos
string prefix = "AURUM_KZ_";

//+------------------------------------------------------------------+
int OnInit()
{
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   BorrarObjetos();
}

//+------------------------------------------------------------------+
int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double &open[],
                const double &high[],
                const double &low[],
                const double &close[],
                const long &tick_volume[],
                const long &volume[],
                const int &spread[])
{
   BorrarObjetos();
   DibujarZonas();
   if(MostrarPanel) DibujarPanel();
   return(rates_total);
}

//+------------------------------------------------------------------+
void DibujarZonas()
{
   datetime ahora = TimeCurrent();

   int diasDibujados = 0;
   int offset        = 0;

   // FIX: iterate by calendar day but count only actual trading days drawn,
   // so weekends are skipped without wasting one of the DiasAtras slots.
   while(diasDibujados < DiasAtras && offset < DiasAtras + 10)
   {
      datetime baseDay = ahora - offset * 86400;
      offset++;

      MqlDateTime dt;
      TimeToStruct(baseDay, dt);

      // Saltar fines de semana
      if(dt.day_of_week == 0 || dt.day_of_week == 6) continue;

      diasDibujados++;

      // ---- KILL ZONE ASIA ----
      // The Asian KZ starts at midnight UTC, so it belongs to the current day.
      // If Asia_Inicio_H >= Asia_Fin_H we treat it as crossing midnight (edge case).
      if(MostrarAsia)
      {
         datetime asiaIni = ConstructDatetime(dt.year, dt.mon, dt.day, Asia_Inicio_H, Asia_Inicio_M, 0);
         datetime asiaFin = ConstructDatetime(dt.year, dt.mon, dt.day, Asia_Fin_H,   Asia_Fin_M,   0);

         // If the zone crosses midnight, end time is on the next calendar day
         if(Asia_Fin_H < Asia_Inicio_H || (Asia_Fin_H == Asia_Inicio_H && Asia_Fin_M <= Asia_Inicio_M))
            asiaFin += 86400;

         string nomAsia = prefix + "ASIA_RECT_" + IntegerToString(diasDibujados);
         DibujarRectangulo(nomAsia, asiaIni, asiaFin, ColorAsia, "Asia Kill Zone");

         if(LineaAperturaASIA)
         {
            string nomAsiaL = prefix + "ASIA_LINE_" + IntegerToString(diasDibujados);
            DibujarLineaVertical(nomAsiaL, asiaIni, ColorLineaASIA, "ASIA Open");
         }
      }

      // ---- KILL ZONE LONDRES ----
      if(MostrarLondres)
      {
         datetime lonIni = ConstructDatetime(dt.year, dt.mon, dt.day, Londres_Inicio_H, Londres_Inicio_M, 0);
         datetime lonFin = ConstructDatetime(dt.year, dt.mon, dt.day, Londres_Fin_H,   Londres_Fin_M,   0);

         string nomLon = prefix + "LON_RECT_" + IntegerToString(diasDibujados);
         DibujarRectangulo(nomLon, lonIni, lonFin, ColorLondres, "London Kill Zone");

         if(LineaAperturaLON)
         {
            string nomLonL = prefix + "LON_LINE_" + IntegerToString(diasDibujados);
            DibujarLineaVertical(nomLonL, lonIni, ColorLineaLON, "LON Open");
         }
      }

      // ---- KILL ZONE NUEVA YORK ----
      if(MostrarNY)
      {
         datetime nyIni = ConstructDatetime(dt.year, dt.mon, dt.day, NY_Inicio_H, NY_Inicio_M, 0);
         datetime nyFin = ConstructDatetime(dt.year, dt.mon, dt.day, NY_Fin_H,   NY_Fin_M,   0);

         string nomNY = prefix + "NY_RECT_" + IntegerToString(diasDibujados);
         DibujarRectangulo(nomNY, nyIni, nyFin, ColorNY, "NY Kill Zone");

         if(LineaAperturaNY)
         {
            string nomNYL = prefix + "NY_LINE_" + IntegerToString(diasDibujados);
            DibujarLineaVertical(nomNYL, nyIni, ColorLineaNY, "NY Open");
         }
      }
   }
}

//+------------------------------------------------------------------+
void DibujarRectangulo(string nombre, datetime t1, datetime t2, color col, string tooltip)
{
   double chartHigh = ChartGetDouble(0, CHART_PRICE_MAX);
   double chartLow  = ChartGetDouble(0, CHART_PRICE_MIN);

   if(ObjectFind(0, nombre) < 0)
      ObjectCreate(0, nombre, OBJ_RECTANGLE, 0, t1, chartHigh, t2, chartLow);

   ObjectSetInteger(0, nombre, OBJPROP_TIME1,      t1);
   ObjectSetInteger(0, nombre, OBJPROP_TIME2,      t2);
   ObjectSetDouble(0,  nombre, OBJPROP_PRICE1,     chartHigh);
   ObjectSetDouble(0,  nombre, OBJPROP_PRICE2,     chartLow);
   ObjectSetInteger(0, nombre, OBJPROP_COLOR,      col);
   ObjectSetInteger(0, nombre, OBJPROP_STYLE,      STYLE_SOLID);
   ObjectSetInteger(0, nombre, OBJPROP_WIDTH,      1);
   ObjectSetInteger(0, nombre, OBJPROP_FILL,       true);
   ObjectSetInteger(0, nombre, OBJPROP_BACK,       true);
   ObjectSetInteger(0, nombre, OBJPROP_SELECTABLE, false);
   ObjectSetString(0,  nombre, OBJPROP_TOOLTIP,    tooltip);
}

//+------------------------------------------------------------------+
void DibujarLineaVertical(string nombre, datetime t, color col, string label)
{
   if(ObjectFind(0, nombre) < 0)
      ObjectCreate(0, nombre, OBJ_VLINE, 0, t, 0);

   ObjectSetInteger(0, nombre, OBJPROP_TIME1,      t);
   ObjectSetInteger(0, nombre, OBJPROP_COLOR,      col);
   ObjectSetInteger(0, nombre, OBJPROP_STYLE,      EstiloLinea);
   ObjectSetInteger(0, nombre, OBJPROP_WIDTH,      GrosorLinea); // FIX: was GrosroLinea
   ObjectSetInteger(0, nombre, OBJPROP_BACK,       false);
   ObjectSetInteger(0, nombre, OBJPROP_SELECTABLE, false);
   ObjectSetString(0,  nombre, OBJPROP_TOOLTIP,    label);
}

//+------------------------------------------------------------------+
void DibujarPanel()
{
   datetime ahora = TimeCurrent();
   MqlDateTime dtNow;
   TimeToStruct(ahora, dtNow);

   int minActual = dtNow.hour * 60 + dtNow.min;

   int lonIniMin  = Londres_Inicio_H * 60 + Londres_Inicio_M;
   int lonFinMin  = Londres_Fin_H    * 60 + Londres_Fin_M;
   int nyIniMin   = NY_Inicio_H      * 60 + NY_Inicio_M;
   int nyFinMin   = NY_Fin_H         * 60 + NY_Fin_M;
   int asiaIniMin = Asia_Inicio_H    * 60 + Asia_Inicio_M;
   int asiaFinMin = Asia_Fin_H       * 60 + Asia_Fin_M;

   // Asia may cross midnight — handle wrap-around
   bool enAsia;
   if(asiaFinMin > asiaIniMin)
      enAsia = (minActual >= asiaIniMin && minActual < asiaFinMin);
   else
      enAsia = (minActual >= asiaIniMin || minActual < asiaFinMin);

   bool enLon = (minActual >= lonIniMin && minActual < lonFinMin);
   bool enNY  = (minActual >= nyIniMin  && minActual < nyFinMin);

   string estadoAsia, estadoLon, estadoNY;

   // Asia status
   if(enAsia) {
      int restMin = (asiaFinMin > minActual) ? asiaFinMin - minActual : (asiaFinMin + 1440 - minActual);
      estadoAsia = "ACTIVA  (" + IntegerToString(restMin) + " min restantes)";
   } else {
      int espMin;
      if(minActual < asiaIniMin)
         espMin = asiaIniMin - minActual;
      else
         espMin = (1440 - minActual) + asiaIniMin;
      if(espMin > 60)
         estadoAsia = "Cerrada";
      else
         estadoAsia = "En " + IntegerToString(espMin) + " min";
   }

   if(enLon) {
      int restMin = lonFinMin - minActual;
      estadoLon = "ACTIVA  (" + IntegerToString(restMin) + " min restantes)";
   } else if(minActual < lonIniMin) {
      int espMin = lonIniMin - minActual;
      estadoLon = "En " + IntegerToString(espMin) + " min";
   } else {
      estadoLon = "Cerrada";
   }

   if(enNY) {
      int restMin = nyFinMin - minActual;
      estadoNY = "ACTIVA  (" + IntegerToString(restMin) + " min restantes)";
   } else if(minActual < nyIniMin) {
      int espMin = nyIniMin - minActual;
      estadoNY = "En " + IntegerToString(espMin) + " min";
   } else {
      estadoNY = "Cerrada";
   }

   string zonaActiva = "Fuera de Kill Zone";
   if(enLon && enNY)        zonaActiva = "LONDON + NY OVERLAP";
   else if(enAsia && enLon) zonaActiva = "ASIA + LONDON OVERLAP";
   else if(enLon)           zonaActiva = "LONDON KILL ZONE";
   else if(enNY)            zonaActiva = "NY KILL ZONE";
   else if(enAsia)          zonaActiva = "ASIA KILL ZONE";

   // FIX: Build panel time labels dynamically from input variables
   // instead of hardcoded strings.
   string asiaLabel = "[ASIA]  TOKYO  "
                   + IntegerToString(Asia_Inicio_H) + ":"
                   + (Asia_Inicio_M < 10 ? "0" : "") + IntegerToString(Asia_Inicio_M)
                   + "-"
                   + IntegerToString(Asia_Fin_H) + ":"
                   + (Asia_Fin_M < 10 ? "0" : "") + IntegerToString(Asia_Fin_M)
                   + " UTC";

   string lonLabel = "[LON]  LONDON  "
                   + IntegerToString(Londres_Inicio_H) + ":"
                   + (Londres_Inicio_M < 10 ? "0" : "") + IntegerToString(Londres_Inicio_M)
                   + "-"
                   + IntegerToString(Londres_Fin_H) + ":"
                   + (Londres_Fin_M < 10 ? "0" : "") + IntegerToString(Londres_Fin_M)
                   + " UTC";

   string nyLabel  = "[NY]  NEW YORK  "
                   + IntegerToString(NY_Inicio_H) + ":"
                   + (NY_Inicio_M < 10 ? "0" : "") + IntegerToString(NY_Inicio_M)
                   + "-"
                   + IntegerToString(NY_Fin_H) + ":"
                   + (NY_Fin_M < 10 ? "0" : "") + IntegerToString(NY_Fin_M)
                   + " UTC";

   int px    = PanelX;
   int py    = PanelY;
   int ancho = 280;
   int alto  = 175;  // expanded for Asia row

   CrearRectPanel(prefix+"panel_rect", px-5, py-5, ancho, alto);

   CrearLabel(prefix+"tit",      px+5, py+5,   "* AURUM KILL ZONES *",                       clrGold,        10);
   CrearLabel(prefix+"hora",     px+5, py+22,  "UTC: " + TimeToString(ahora, TIME_MINUTES), clrSilver,       8);

   CrearLabel(prefix+"sep0",     px+5, py+38,  "-------------------------",                 clrDimGray,      7);

   // Asia
   CrearLabel(prefix+"asia_tit", px+5, py+52,  asiaLabel,                                  ColorLineaASIA,  9);
   CrearLabel(prefix+"asia_st",  px+5, py+67,  estadoAsia,                                 enAsia ? clrLime : clrSilver, 8);

   CrearLabel(prefix+"sep1",     px+5, py+82,  "-------------------------",                 clrDimGray,      7);

   // Londres
   CrearLabel(prefix+"lon_tit",  px+5, py+96,  lonLabel,                                   ColorLineaLON,   9);
   CrearLabel(prefix+"lon_st",   px+5, py+111, estadoLon,                                  enLon ? clrLime : clrSilver, 8);

   // NY
   CrearLabel(prefix+"ny_tit",   px+5, py+127, nyLabel,                                    ColorLineaNY,    9);
   CrearLabel(prefix+"ny_st",    px+5, py+142, estadoNY,                                   enNY  ? clrLime : clrSilver, 8);

   CrearLabel(prefix+"sep2",     px+5, py+157, "-------------------------",                 clrDimGray,      7);
   color cZona = (enLon || enNY || enAsia) ? clrYellow : clrGray;
   CrearLabel(prefix+"zona",     px+5, py+169, zonaActiva,                                  cZona,           9);
}

//+------------------------------------------------------------------+
void CrearLabel(string nombre, int x, int y, string texto, color col, int size)
{
   if(ObjectFind(0, nombre) < 0)
      ObjectCreate(0, nombre, OBJ_LABEL, 0, 0, 0);

   ObjectSetInteger(0, nombre, OBJPROP_CORNER,     CORNER_LEFT_UPPER);
   ObjectSetInteger(0, nombre, OBJPROP_XDISTANCE,  x);
   ObjectSetInteger(0, nombre, OBJPROP_YDISTANCE,  y);
   ObjectSetString(0,  nombre, OBJPROP_TEXT,       texto);
   ObjectSetInteger(0, nombre, OBJPROP_COLOR,      col);
   ObjectSetInteger(0, nombre, OBJPROP_FONTSIZE,   size);
   ObjectSetString(0,  nombre, OBJPROP_FONT,       "Arial Bold");
   ObjectSetInteger(0, nombre, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, nombre, OBJPROP_BACK,       false);
}

//+------------------------------------------------------------------+
void CrearRectPanel(string nombre, int x, int y, int w, int h)
{
   if(ObjectFind(0, nombre) < 0)
      ObjectCreate(0, nombre, OBJ_RECTANGLE_LABEL, 0, 0, 0);

   ObjectSetInteger(0, nombre, OBJPROP_XDISTANCE,    x);
   ObjectSetInteger(0, nombre, OBJPROP_YDISTANCE,    y);
   ObjectSetInteger(0, nombre, OBJPROP_XSIZE,        w);
   ObjectSetInteger(0, nombre, OBJPROP_YSIZE,        h);
   ObjectSetInteger(0, nombre, OBJPROP_BGCOLOR,      C'20,20,35');
   ObjectSetInteger(0, nombre, OBJPROP_BORDER_COLOR, C'60,60,90');
   ObjectSetInteger(0, nombre, OBJPROP_CORNER,       CORNER_LEFT_UPPER);
   ObjectSetInteger(0, nombre, OBJPROP_STYLE,        STYLE_SOLID);
   ObjectSetInteger(0, nombre, OBJPROP_WIDTH,        1);
   ObjectSetInteger(0, nombre, OBJPROP_BACK,         false);
   ObjectSetInteger(0, nombre, OBJPROP_SELECTABLE,   false);
}

//+------------------------------------------------------------------+
datetime ConstructDatetime(int year, int mon, int day, int hour, int min, int sec)
{
   MqlDateTime dt;
   dt.year        = year;
   dt.mon         = mon;
   dt.day         = day;
   dt.hour        = hour;
   dt.min         = min;
   dt.sec         = sec;
   dt.day_of_week = 0;
   dt.day_of_year = 0;
   return StructToTime(dt);
}

//+------------------------------------------------------------------+
void BorrarObjetos()
{
   int total = ObjectsTotal(0, -1, -1);
   for(int i = total - 1; i >= 0; i--)
   {
      string nombre = ObjectName(0, i);
      if(StringFind(nombre, prefix) == 0)
         ObjectDelete(0, nombre);
   }
}
//+------------------------------------------------------------------+