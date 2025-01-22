# Copyright (C) 2024 - Scalizer (<https://www.scalizer.fr>).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

import os
import pickle

from .logging import get_logger

logger = get_logger(__name__)

try:
    import psycopg
    from psycopg.rows import dict_row
    import pymssql
    import pyodbc
    import mysql.connector
except Exception as err:
    logger.error(err)
    pass


class SqlConnection:
    _name = "SQL"
    connection = None

    def __init__(self, db_type, url, dbname, username, password, port=5432, **kwargs):
        self.db_type = db_type
        self.url = url
        self.dbname = dbname
        self.username = username
        self.password = password
        self.port = port
        if self.db_type == "postgresql":
            self.connection = psycopg.connect(
                user=self.username,
                password=self.password,
                host=self.url,
                dbname=self.dbname,
                port=self.port,
                row_factory=dict_row
            )
        elif self.db_type == "mysql":
            self.connection = mysql.connector.connect(
                host=self.url,
                user=self.username,
                password=self.password,
                database=self.dbname
            )
        elif self.db_type == "mssql":
            driver = 'ODBC Driver 18 for SQL Server'
            connectionString = f'DRIVER={driver};SERVER={url};DATABASE={dbname};UID={username};Encrypt=no;PWD={password}'
            try:
                self.connection = pyodbc.connect(connectionString)
            except:
                print(
                    "https://learn.microsoft.com/en-us/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server")

    def execute(self, query, cache=False):
        if cache:
            if not os.path.exists('.cache'):
                logger.info("Create cache directory .cache")
                os.makedirs('.cache')
            cache_filename = ".cache/" + cache + ".pickle"
            if os.path.exists(cache_filename):
                with open(cache_filename, "rb") as infile:
                    results = pickle.load(infile)
                return results
        cursor = self.connection.cursor()
        cursor.execute(query)

        columns = [column[0] for column in cursor.description]
        unique_columns = []
        column_count = {}
        for column in columns:
            if column in column_count:
                column_count[column] += 1
                unique_columns.append(f"{column}_{column_count[column]}")
            else:
                column_count[column] = 0
                unique_columns.append(column)

        results = []
        for row in cursor.fetchall():
            results.append(dict(zip(unique_columns, row)))
        cursor.close()
        if cache:
            with open(cache_filename, "wb") as outfile:
                pickle.dump(results, outfile)
        return results
