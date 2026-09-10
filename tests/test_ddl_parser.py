import pytest

from ddldelta.ddl_parser import (
    DIALECTS, parse_mysql_ddl, parse_sqlserver_ddl, parser_for)

SQLSERVER_DDL = """
CREATE TABLE [dbo].[101_ID_MAKES](
    [make_id] [int] NOT NULL,
    [make_name] [nvarchar](100) NULL,
    [price] [money] NULL,
    [updated] [datetime2](7) NOT NULL,
)
"""


def test_sqlserver_tabelle_und_spalten():
    tabelle, spalten, _ = parse_sqlserver_ddl(SQLSERVER_DDL)
    assert tabelle == "101_ID_MAKES"
    assert list(spalten) == ["make_id", "make_name", "price", "updated"]
    assert spalten["make_id"] == ("INT", True)
    assert spalten["make_name"] == ("VARCHAR(100)", False)
    assert spalten["price"] == ("NUMBER(19,4)", False)
    assert spalten["updated"] == ("TIMESTAMP_NTZ", True)


def test_parser_for_liefert_parser_je_dialekt():
    tabelle, _, _ = parser_for("tsql")(SQLSERVER_DDL)
    assert tabelle == "101_ID_MAKES"


def test_parser_for_unbekannter_dialekt_wirft_verstaendlichen_fehler():
    # Tippfehler in der Registry sollen sofort auffallen, nicht bei der
    # ersten Lieferung.
    with pytest.raises(ValueError, match="unknown SQL dialect"):
        parser_for("sqlserver")   # heisst bei sqlglot tsql


# Auszug aus structure_table/bve_marque.sql (Lieferung 3.46.2_AM20260720),
# inkl. Dump-Rahmen, PRIMARY KEY und KEY-Zeilen.
MYSQL_DDL = """
DROP TABLE IF EXISTS `bve_marque`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
CREATE TABLE `bve_marque` (
  `id` smallint(5) unsigned NOT NULL,
  `nom` varchar(30) NOT NULL,
  `codeetai` varchar(3) DEFAULT NULL,
  `prix` decimal(10,2) DEFAULT NULL,
  `dateprix` datetime DEFAULT NULL,
  `flagunique` tinyint(1) unsigned DEFAULT '0',
  `generique` bit(1) DEFAULT NULL,
  `typeequivalence` enum('COMMERCIALE','EAN13') NOT NULL,
  `commentaire` text,
  PRIMARY KEY (`id`),
  KEY `idx_mrq_groupemarquemarque` (`idgroupemarque`,`id`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8;
"""

# structure_table/itf_xat2dictionnaireconversion.sql hat KEINEN Dump-Rahmen.
MYSQL_DDL_OHNE_RAHMEN = """
CREATE TABLE `itf_xat2dictionnaireconversion`
(
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `categorievaleur` varchar(100) NOT NULL,

  PRIMARY KEY (`id`)

) ENGINE=MyISAM DEFAULT CHARSET=utf8;
"""


def test_mysql_namen_in_original_schreibweise():
    tabelle, spalten, _ = parse_mysql_ddl(MYSQL_DDL)
    assert tabelle == "bve_marque"
    assert list(spalten) == [
        "id", "nom", "codeetai", "prix", "dateprix", "flagunique",
        "generique", "typeequivalence", "commentaire",
    ]


def test_mysql_typen_und_nullability():
    _, spalten, _ = parse_mysql_ddl(MYSQL_DDL)
    assert spalten["id"] == ("SMALLINT", True)          # display-width/unsigned weg
    assert spalten["nom"] == ("VARCHAR(30)", True)
    assert spalten["codeetai"] == ("VARCHAR(3)", False)
    assert spalten["prix"] == ("DECIMAL(10,2)", False)  # numerische Args bleiben
    assert spalten["dateprix"] == ("TIMESTAMP_NTZ", False)
    assert spalten["flagunique"] == ("TINYINT", False)  # DEFAULT '0' ist nullable
    assert spalten["generique"] == ("BOOLEAN", False)   # bit -> true/false im CSV
    assert spalten["typeequivalence"] == ("VARCHAR", True)  # Werteliste verworfen
    assert spalten["commentaire"] == ("VARCHAR", False)


def test_mysql_ohne_dump_rahmen():
    tabelle, spalten, _ = parse_mysql_ddl(MYSQL_DDL_OHNE_RAHMEN)
    assert tabelle == "itf_xat2dictionnaireconversion"
    assert spalten["id"] == ("INT", True)               # AUTO_INCREMENT ignoriert
    assert spalten["categorievaleur"] == ("VARCHAR(100)", True)


def test_mysql_unbekannter_typ_laeuft_durch():
    # Regel: unbekannte Typen werden durchgereicht und scheitern laut beim
    # Deploy - nicht schon beim Parsen.
    _, spalten, _ = parse_mysql_ddl("CREATE TABLE `x` (\n  `g` geometry NOT NULL,\n)")
    assert spalten["g"] == ("GEOMETRY", True)


def test_sqlserver_ohne_create_table_wirft_verstaendlichen_fehler():
    with pytest.raises(ValueError, match="no CREATE TABLE"):
        parse_sqlserver_ddl("-- nur ein Kommentar, keine Tabelle")


def test_mysql_ohne_create_table_wirft_verstaendlichen_fehler():
    with pytest.raises(ValueError, match="no CREATE TABLE"):
        parse_mysql_ddl("SET NAMES utf8;")


SQLSERVER_DDL_MIT_PK = SQLSERVER_DDL + """
GO
ALTER TABLE [dbo].[101_ID_MAKES] ADD CONSTRAINT [PK_101_ID_MAKES] PRIMARY KEY CLUSTERED ([make_id], [wks_lang]) ON [PRIMARY]
GO
"""


def test_sqlserver_mehrspaltiger_pk_in_ddl_reihenfolge():
    _, _, key = parse_sqlserver_ddl(SQLSERVER_DDL_MIT_PK)
    assert key == ("make_id", "wks_lang")


def test_sqlserver_ohne_pk_leerer_schluessel():
    assert parse_sqlserver_ddl(SQLSERVER_DDL)[2] == ()


def test_mysql_einspaltiger_pk_und_using_hash():
    assert parse_mysql_ddl(MYSQL_DDL)[2] == ("id",)
    ddl = ("CREATE TABLE `x` (\n  `a` int NOT NULL,\n  `b` int NOT NULL,\n"
           "  PRIMARY KEY (`b`,`a`) USING HASH,\n) ENGINE=MyISAM;")
    assert parse_mysql_ddl(ddl)[2] == ("b", "a")


def test_mysql_ohne_pk_leerer_schluessel():
    assert parse_mysql_ddl(MYSQL_DDL_OHNE_RAHMEN.replace(
        "  PRIMARY KEY (`id`)\n", ""))[2] == ()


# ---- sqlglot-Umstellung (plan 2026-08-25-ddl-parser-sqlglot) ----------------

SQLSERVER_MIT_GO = """CREATE TABLE [dbo].[T]
(
[a] [int] NOT NULL,
[b] [varchar] (5) COLLATE Latin1_General_CI_AS NULL
) ON [PRIMARY]
GO
ALTER TABLE [dbo].[T] ADD CONSTRAINT [PK_T] PRIMARY KEY CLUSTERED ([a], [b]) ON [PRIMARY]
GO
"""


def test_sqlserver_go_batches_werden_getrennt():
    # sqlglot kennt GO nicht: ohne Split degradiert die ganze Datei still zu
    # einem Command-Knoten und die DDL waere verloren.
    tabelle, spalten, _ = parse_sqlserver_ddl(SQLSERVER_MIT_GO)
    assert tabelle == "T"
    assert list(spalten) == ["a", "b"]


def test_sqlserver_pk_aus_alter_constraint():
    # Nagelt die Baumnavigation fest: sqlglot baut fuer diese Form KEINEN
    # exp.PrimaryKey, die Spaltenliste haengt im ClusteredColumnConstraint
    # (gemessen 2026-08-25, sqlglot 30.17). Bricht bei einem Update sichtbar.
    _, _, key = parse_sqlserver_ddl(SQLSERVER_MIT_GO)
    assert key == ("a", "b")


def test_explizites_null_ist_nicht_not_null():
    # sqlglot bildet auch ein explizites NULL als NotNullColumnConstraint ab
    # (allow_null=True) - die Klasse allein zu pruefen waere falsch.
    _, spalten, _ = parse_sqlserver_ddl(SQLSERVER_MIT_GO)
    assert spalten["a"][1] is True
    assert spalten["b"][1] is False


def test_unparsebare_ddl_wirft_valueerror_statt_still_leer_zu_sein():
    # sqlglot faellt bei unbekannter Syntax auf einen Command-Knoten zurueck,
    # ohne zu werfen. Eine still leere Spaltenliste wuerde bis in den
    # Generator und den positionalen COPY durchschlagen.
    with pytest.raises(ValueError, match="no CREATE TABLE"):
        parse_sqlserver_ddl("EXEC sp_irgendwas @a = 1")


def test_create_table_ohne_spalten_wirft_valueerror():
    ohne_spalten = "CREATE TABLE `x` (\n  PRIMARY KEY (`a`)\n)"
    with pytest.raises(ValueError, match="without columns"):
        parse_mysql_ddl(ohne_spalten)
