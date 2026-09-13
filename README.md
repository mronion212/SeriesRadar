# SeriesRadar

Een rustige, Nederlandse webapp voor **nieuwe Nederlandse series en nieuwe seizoenen**. Nieuws wordt per serietitel gebundeld. Python 3.13, SQLite en Docker Compose; geen externe Python-pakketten of API-sleutels nodig.

## Gebruik

- **Series** opent standaard op **Alle producties**. Kies **Nieuw seizoen** of **Alle producties**, filter op status en sorteer op laatste nieuws of titel.
- Klik op een serietitel voor het dossier: producties/seizoenen met hun eigen status, de onderbouwing en alle gekoppelde nieuwsartikelen, op publicatiedatum gesorteerd.
- **Te beoordelen** bevat berichten waarvoor titel, herkomst of nieuwe productie onvoldoende duidelijk is. Met **Beoordelen / koppelen** kies je de serietitel, het type en eventueel het seizoennummer.
- Gebruik dezelfde serietitel om artikelen te bundelen. Een correctie verplaatst alleen dat artikel. Hoofdletters, leestekens en accenten worden bij het groeperen genegeerd. Verschillende series met dezelfde naam kun je onderscheiden met bijvoorbeeld een jaartal in de titel.
- Je kunt notities bewaren, een artikel afvinken voor TVDB of negeren. Onder **Buiten selectie / genegeerd** kun je een artikel ook herstellen. Een handmatige beoordeling kan de automatische selectie overrulen.
- Er wordt niets automatisch op TVDB geplaatst; de link opent alleen de zoekpagina.

### Productiestatus

| Status | Betekenis |
| --- | --- |
| Aangekondigd | Aankondiging gevonden. |
| Release gepland | Een concrete releaseplanning gevonden; de opnamestatus is daarmee niet bewezen. |
| In productie | Expliciet bericht over gestarte/lopende opnames of productie. |
| Geproduceerd | Een bericht noemt afgeronde opnames/productie. Dit is geen garantie dat iedere stap van de postproductie klaar is. |
| Beschikbaar | Expliciet bericht dat de serie beschikbaar is. |
| Onbekend | Het fragment bevat geen betrouwbare aanwijzing of meldt uitstel/annulering. Lees de onderbouwing. |

Een releasedatum, trailer of verstreken kalenderdatum bewijst **niet** dat de serie geproduceerd of beschikbaar is. De app schuift een status daarom niet automatisch door na een datum. Per vastgestelde productie wordt de verst gevorderde expliciete status gebruikt: een generieke, latere aankondiging maakt afgeronde opnames niet ongedaan. Een minstens even recente handmatige beoordeling of expliciete annulering/uitstel krijgt voorrang. Publicatiedata bepalen de volgorde, niet het moment waarop de crawler een oud bericht vindt.

**Seizoenen blijven gescheiden.** Een beschikbaar seizoen 1 maakt seizoen 2 niet beschikbaar. Een bericht zonder vastgesteld seizoen krijgt een apart blok en verandert de status van een genummerd seizoen niet. Nieuwe series worden als eerste seizoen gegroepeerd. ‘Nieuw seizoen’ zonder nummer blijft een aparte, onzekere groep; koppel die berichten handmatig zodra je het nummer weet.

### Hoe streng is de selectie?

De app gebruikt conservatieve tekstregels op feedkoppen en korte fragmenten. Hij zoekt expliciet naar een nieuwe serie of nieuw seizoen, een herkenbare serietitel en Nederlandse context. Bekende titels worden in andere berichten herkend. Kijktips, recensies, verzameloverzichten en veel niet-relevant nieuws gaan buiten de hoofdselectie. Bij onduidelijkheid wordt geen serietitel verzonnen.

Dit is **geen AI die alle artikelen volledig leest**, geen volledige seriecatalogus en geen uitputtende controle tegen de volledige TVDB-database. ‘Nieuwe serie’ betekent dat het nieuws die productie als nieuw beschrijft; niet dat de titel nog ontbreekt op TVDB. Ook reality- en documentaireseries kunnen voorkomen. Reboots kunnen een bestaande titel gebruiken. Controleer automatische koppelingen voordat je informatie overneemt. Bij een ontbrekende titel, meerdere series in één bericht, een afwijkende schrijfwijze of weinig context is handmatig koppelen nodig. Een meer-serie-artikel kan handmatig aan één dossier worden gekoppeld; automatische koppeling aan meerdere dossiers wordt niet gedaan.

## Dossiers voor IMDb en TVDB

Het serieoverzicht gebruikt kaarten met status, platform, nieuwsaantal en de voortgang van het dossier. Klik op een serie en kies de productie of het seizoen. Het dossier heeft tabbladen voor het overzicht, cast en crew, bronnen en nieuws, en IMDb/TVDB.

- Gegevens: titels, synopsis, land, taal, genres, netwerk/omroep, streamingplatform, productiebedrijf, coproductiepartners, cast en personages, regie, scenario, bedenkers, producenten, releaseplanning, afleveringen, speelduur en officiële links.
- Expliciete gegevens uit feeds worden automatisch voorgesteld met bronvermelding. Onder **Bronnen & nieuws** kun je een directe persbericht-URL laten uitlezen. Een Google Nieuws-doorverwijzing of een website die JavaScript of een login vereist, is hiervoor niet altijd geschikt. De pagina moet de serietitel noemen.
- Gekoppelde perspagina's worden na 24 uur opnieuw gecontroleerd, maximaal vier per scanronde. Dit staat los van de nieuwsfeeds die iedere 30 minuten worden gescand.
- Met **Gegevens aanvullen** kun je ieder veld, de bronlink en de onderbouwing corrigeren. Handmatige waarden worden niet overschreven door nieuwe scans. Cast en andere gegevens blijven per productie/seizoen gescheiden.
- Niet gevonden betekent **Nog onbekend**. Automatische voorstellen zijn tekstherkenning en moeten worden gecontroleerd. De voortgang telt elf basisvelden; het is geen garantie dat een inzending aan alle platformregels voldoet.
- Onder **IMDb / TVDB** kun je het dossier kopiëren of als JSON downloaden. Dit is een invoerhulp, geen automatisch importformaat of automatische inzending bij die platforms. Schrijf een eigen synopsis en controleer de rechten op beeldmateriaal.

Alle dossiergegevens en gekoppelde bronnen staan in dezelfde SQLite-database en worden dus meegenomen in de back-up.

## Nieuwsbronnen toevoegen

Ga naar **Bronnen → Bron toevoegen**:

1. Geef de bron een naam.
2. Kies **RSS / Atom-feed** of **Google Nieuws-zoekopdracht**.
3. Plak de feedlink of vul een zoekopdracht in.
4. Klik **Bron testen** om te zien of de bron bereikbaar is en voorbeelden te bekijken.
5. Klik **Bron opslaan**. Klik eventueel daarna **Nu scannen**.

Voor een website zonder feed kun je bijvoorbeeld gebruiken:

```text
site:producent.nl ("nieuwe serie" OR "nieuw seizoen" OR opnames) when:90d
```

Gebruik voor een feed de echte RSS/Atom-URL, niet de homepage. Alleen publieke HTTPS-feeds worden geaccepteerd; lokale/private adressen en redirects daarnaartoe worden geweigerd. Via **Wijzigen** kun je naam en zoekopdracht/feed veranderen en **Bron actief** uitzetten om te pauzeren. Bestaande artikelen blijven bewaard.

De ingebouwde bronnen staan in `sources.json`; wijzigingen via de website worden als overrides in SQLite opgeslagen en hebben voorrang. Custom bronnen staan ook in SQLite. Je hoeft voor normaal bronbeheer geen bestand te wijzigen en de container niet te herstarten. Back-ups bevatten dus zowel je broninstellingen als beoordelingen.

Er zijn standaard twintig bronnen/zoekfeeds voor AVROTROS, RTL/Videoland, Talpa/SBS6, NPO/omroepen, Nederlandse producties bij streamers, producenten en vakmedia. AVROTROS en Broadcast Magazine hebben directe feeds; daarnaast zijn er gerichte Google Nieuws-zoekopdrachten, onder andere voor FilmVandaag, TVgids, TVvisie en landelijke nieuwsmedia. Directe feeds hebben de voorkeur als ze beschikbaar zijn. Google kan berichten vertraagd indexeren of missen. De app kan geen volledige dekking of voorsprong op iedereen garanderen. Besloten perslijsten en sociale media worden niet uitgelezen.

## Starten op je VPS

Installeer Docker Engine met de Compose-plugin en voer uit:

```sh
git clone https://github.com/mronion212/SeriesRadar.git
cd SeriesRadar
cp .env.example .env
nano .env
# Vul een sterk ADMIN_PASSWORD in.
docker compose up -d --build
docker compose logs -f --tail=50
```

Er wordt een image `seriesradar:local` gebouwd. De container draait als een gebruiker zonder rootrechten met een alleen-lezen bestandssysteem en een schrijfbaar databasevolume. De Compose-poort is alleen op localhost bereikbaar. Zet je HTTPS-reverseproxy ervoor, bijvoorbeeld Caddy op dezelfde VPS:

```caddyfile
series.jouwdomein.nl {
    reverse_proxy 127.0.0.1:8080
}
```

Laat DNS naar de VPS wijzen. Een reverseproxy in een andere container moet via een gedeeld Docker-netwerk naar `seriesradar:8080` verbinden, niet naar zijn eigen localhost. Gebruik HTTPS voor internettoegang: de app gebruikt HTTP Basic-login met de gegevens uit `.env`.

Zonder domein kun je vanaf je computer een tunnel gebruiken:

```sh
ssh -L 8080:127.0.0.1:8080 gebruiker@je-vps
```

Open daarna http://localhost:8080 en log in.

## Scans en instellingen

Bij het starten voert de app een scan uit, daarna 30 minuten na afronding van iedere scan. De scan zelf duurt doorgaans seconden, maar trage bronnen kunnen de ronde verlengen. Geen aparte cron nodig. De container moet blijven draaien. Eén container per database gebruiken; de scheduler draait in hetzelfde proces. Handmatig scannen start geen overlappende tweede scan. De website haalt elke 10 seconden het bijgewerkte overzicht op.

In `.env`:

- `ADMIN_USER`: standaard `admin`.
- `ADMIN_PASSWORD`: verplicht voor de Docker-configuratie.
- `PORT`: lokale VPS-poort, standaard `8080`.
- `SCAN_INTERVAL_SECONDS`: standaard `1800`, minimum `60`.

De zoekfeeds vragen standaard tot 180 dagen terug. Google bepaalt welke resultaten en datums worden teruggegeven; de directe feed bepaalt haar eigen terugblik. De eerste scan importeert dus ook oudere aankondigingen. Gelijke koppen worden niet herhaald toegevoegd. Andere koppen over dezelfde serie blijven aparte artikelen; een uitgever kan bij een gewijzigde kop nog een dubbel artikel opleveren.

## Data, updates en back-ups

Alles staat in Docker-volume `radar-data`, in `radar.sqlite3`. Herstarten of opnieuw bouwen wist niets. Gebruik **geen** `docker compose down -v` als je de gegevens wilt bewaren. De upgrade van de eerste versie voegt kolommen toe en bewaart artikelen, notities en beoordelingen. De serieclassificatie wordt opnieuw uit de bestaande fragmenten afgeleid; eerder handmatig gekozen titels blijven behouden.

Een consistente back-up maken terwijl de app draait:

```sh
docker compose exec seriesradar python -c "import sqlite3; s=sqlite3.connect('/data/radar.sqlite3'); d=sqlite3.connect('/data/backup.sqlite3'); s.backup(d); d.close(); s.close()"
docker compose cp seriesradar:/data/backup.sqlite3 ./backup.sqlite3
```

Bewaar de back-up ook buiten de VPS. Bij herstel stop je de app en vervang je de database in het volume door de back-up. Verwijder eventuele oude WAL/SHM-bestanden vóór herstart; houd UID/GID 10001 als eigenaar.

Bij een code-update:

```sh
git pull
docker compose up -d --build
```

## Ontwikkelen en testen

Python 3.13, uitsluitend standaardbibliotheek. Node is alleen nodig voor de optionele JavaScript-syntaxcontrole.

```sh
python app.py
python -m unittest discover -s tests -v
python tests/http_smoke.py
node --check public/app.js
```

Lokaal zonder instellingen luistert de openbare website op 127.0.0.1:8080; beheer vereist ADMIN_PASSWORD. Voor een netwerkbinding weigert hij te starten zonder wachtwoord. `python app.py --scan-once` voert één echte scan uit. `/health` controleert HTTP en SQLite; individuele bronfouten staan onder Bronnen.

De tests dekken onder meer seizoenisolatie, titelherkenning, foutieve koppelingen, statusregels, bronvalidatie, duurzame broninstellingen, dubbele berichten en authenticatie. De GitHub-workflow test ook het bouwen en starten van de Docker-image. De lokale Docker-engine moet draaien om dat lokaal te kunnen reproduceren.

## Uitgebreidere ontdekking en metadata

De selectie herkent ook spelshows, quizzen, partygames, reality, datingprogramma’s, talentenjachten en documentaires. Nieuwe zoekfeeds dekken genres en aankondigingen breder. Broadcast Magazine heeft ook een aparte productiefeed. De twee gemelde voorbeeldartikelen worden eenmaal rechtstreeks geïmporteerd als ze nog ontbreken, ook als ze uit de actuele feed zijn verdwenen. Eigen broninstellingen blijven voorrang houden.

Per scan worden maximaal acht directe artikelpagina’s uitgelezen (maximaal eenmaal per dag per artikel) en vier TVDB-kandidaten gecontroleerd (maximaal eenmaal per week). TVDB controleren in het dossier kan een controle vervroegen, met een dagcache. Een TVDB-kandidaat wordt gevonden via de titel als URL-slug; alleen een exacte titel, een geldig serie-ID en een Nederlands productieland worden automatisch bevestigd. Andere schrijfwijzen, ontbrekende landen en onbereikbare pagina’s blijven onbevestigd en hebben een handmatige zoeklink. Dit is geen volledige TVDB-zoekmachine. De TVDB-controle staat los van het handmatige vinkje ‘Verwerkt voor TVDB’.

Volledige RSS-inhoud en directe pagina’s leveren meer expliciete gegevens op: synopsisvoorstellen, producenten, taal, genres, afleveringen, netwerk en releaseplanning. De oorspronkelijke bron blijft bij ieder veld staan. De taal van een nieuwsartikel bewijst niet de originele taal van een serie. Ontbrekende jaartallen worden niet gegokt. Synopsisvoorstellen zijn brontekst en moeten vóór inzending worden herschreven. Google Nieuws-links worden niet automatisch omzeild: voor zulke berichten blijven de feedgegevens beschikbaar; directe feeds en handmatig gekoppelde perspagina’s leveren de volledige tekst.

Het overzicht vult ultrawide-schermen met extra kaartkolommen. Vanaf 1800 pixels gebruikt het dossier twee sectiekolommen. Mobiele breakpoints blijven behouden. Er zijn geen betaalde AI-oproepen toegevoegd.

Beschikbaarheidsnieuws (zoals ‘sinds vrijdag te zien op Videoland’) wordt apart gezocht. Een bericht zonder seizoennummer mag alleen het enige eerste-seizoendossier bijwerken; bij meerdere seizoenen blijft het apart ter beoordeling. Een toekomstige formulering als ‘vanaf 4 september in zijn geheel te streamen’ betekent Release gepland, niet Beschikbaar. De uitzenddatum is ook zichtbaar op de overzichtskaart.

## Reality en programma’s zonder bevestigd seizoen

De herkenning gebruikt ook de paginabeschrijving en zinnen uit de artikeltekst die de betreffende titel noemen. Schrijfwijzen zoals reality programma, reality-programma, spelprogramma, survivalprogramma en realityshow worden gezamenlijk herkend. Een afkorting vóór de uitgeschreven titel (zoals A.S.S. Anti Survival Show) wordt alleen samengevoegd als de initialen daadwerkelijk overeenkomen.

Een benoemd Nederlands programma met bevestigde beschikbaarheid of concrete releaseplanning verschijnt ook zonder bewezen seizoennummer in het overzicht. Het blijft dan ‘Seizoen niet vastgesteld’; er wordt geen eerste of nieuw seizoen verzonnen. Daarom opent het overzicht standaard met Alle producties. Seizoennummers in URL’s zijn geen classificatiebewijs.

De aangeleverde links voor Wolven, Anti Survival Show en Undercover Lover worden rechtstreeks geprobeerd tijdens de scan. Een geblokkeerde of niet uitleesbare pagina blokkeert andere bronartikelen niet; fouten zijn zichtbaar bij Bronnen en worden maximaal dagelijks opnieuw geprobeerd. Algemene zoekopdrachten voor reality, Net5, Prime Video, programmagidsen en Nederlandstalige producties zijn eveneens uitgebreid. Browserafhankelijke pagina’s, zoals sommige NPO/Streamz-pagina’s en privacygates, kunnen onleesbaar blijven; beschikbare alternatieve bronnen worden wel verwerkt.

## Openbare website, beheer en updates

De homepage en `/api/dashboard` zijn publiek toegankelijk. Bezoekers kunnen series, dossiers en bronartikelen bekijken. Interne notities, de beoordelingswachtrij, broninstellingen en foutdiagnostiek worden niet via de openbare API geleverd.

Open `/admin` voor de beheeromgeving met de bestaande ADMIN_USER / ADMIN_PASSWORD-login. Daar staan scans, bronbeheer, beoordelingen, metadata-import en wijzigingen. Alle POST-endpoints en `/api/admin/dashboard` vereisen serverzijdig authenticatie. Zonder ADMIN_PASSWORD blijft beheer gesloten, ook op localhost. De openbare website blijft bruikbaar.

Alle wijzigingen gaan rechtstreeks op **main**. GitHub en de VPS gebruiken main als standaard; gebruik geen aparte codex-branch. Op de VPS staat de checkout in `/opt/docker/apps/seriesradar`. De bestaande aio-composeconfiguratie blijft behouden. Updaten:

```sh
git -C /opt/docker/apps/seriesradar pull --ff-only origin main
cd /opt/docker
sudo docker compose -p aio --profile seriesradar up -d --build --no-deps seriesradar
```

Een GitHub-push bouwt en test in CI; bovenstaande opdracht werkt de draaiende VPS-container bij.
# AI-onderzoek en bronactualiteit

In **Beheer → Bronnen → AI-onderzoek** kun je een OpenAI API-sleutel opslaan.
Deze staat in de serverdatabase (dus ook in databaseback-ups), wordt nooit in een dashboardantwoord teruggegeven en is uitsluitend via de beveiligde beheerroute te wijzigen.
Als alternatief ondersteunt de app de servervariabele `OPENAI_API_KEY`; een opgeslagen sleutel heeft voorrang.
API-gebruik wordt apart door OpenAI gefactureerd.

Open een seriedossier, kies de productie/het seizoen en klik **Dossier onderzoeken met AI**.
Het onderzoek gebruikt uitsluitend `gpt-5.6-luna`, `reasoning.effort=max`, Responses API en web search.
Er is geen automatische terugval naar een ander model. De app draait maximaal één onderzoek tegelijk, op verzoek van een beheerder.
Het onderzoek vraagt alle dossiervelden op en controleert maximaal tien geraadpleegde bronpagina's op titel, seizoen en het aangehaalde citaat.
Niet bevestigde gegevens worden overgeslagen; handmatige velden houden voorrang. Een gevonden citaat bewijst niet dat de interpretatie klopt: resultaten blijven herkenbaar als AI-voorstel.
Bij een fout blijven eerdere voorstellen staan. Na een herstart kan een onderbroken onderzoek opnieuw worden gestart.

Publieke lezers zien de laatste scan, feedcontrole, eerste vondst en laatste succesvolle artikeluitlezing.
Een mislukte nieuwe poging wist het tijdstip van de vorige succesvolle uitlezing niet.
Google Nieuws-fragmenten worden expliciet als onvolledig gemarkeerd. Koppel een directe bron of gebruik AI-onderzoek om aanvullende bronnen te vinden.
