from asyncio import coroutine
from functools import wraps

from aiopg import create_pool, Pool, Cursor
import psycopg2


class PostgresStore:
    _pool = None
    _connection_params = {}
    _insert_string = "insert into {} ({}) values ({});"
    _update_string = "update {} set ({}) = ({}) where {} = %s;"
    _select_all_string = "select * from {} where ({})"
    _select_selective_column = "select {} from {} where ({})"
    _delete_query = "delete from {} where ({})"


    @classmethod
    def connect(cls, database:str, user:str, password:str, host:str, port:int):
        """
        Sets connection parameters
        """
        cls._connection_params['database'] = database
        cls._connection_params['user'] = user
        cls._connection_params['password'] = password
        cls._connection_params['host'] = host
        cls._connection_params['port'] = port

    @classmethod
    def use_pool(cls, pool:Pool):
        """
        Sets an existing connection pool instead of using connect() to make one
        """
        cls._pool = pool

    @classmethod
    @coroutine
    def get_pool(cls) -> Pool:
        """
        Yields:
            existing db connection pool
        """
        if len(cls._connection_params) < 5:
            raise ConnectionError('Please call SQLStore.connect before calling this method')
        if not cls._pool:
            cls._pool = yield from create_pool(**cls._connection_params)
        return cls._pool

    @classmethod
    @coroutine
    def get_cursor(cls, dict_cursor=False) -> Cursor:
        """
        Yields:
            new client-side cursor from existing db connection pool
        """
        pool = yield from cls.get_pool()
        if dict_cursor:
            cur = yield from pool.cursor(cursor_factory=psycopg2.extras.DictCursor)
        else:
            cur = yield from pool.cursor()
        return cur

    @classmethod
    def make_insert_query(cls, table_name:str, values:dict):
        """
        Creates an insert statement with only chosen fields

        Args:
            table_name: a string indicating the name of the table
            values: a dict of fields and values to be inserted

        Returns:
            query: a SQL string with
            values: a tuple of values to replace placeholder(%s) tokens in query

        """
        keys = ', '.join(values.keys())
        value_place_holder = ' %s,' * len(values)
        query = cls._insert_string.format(table_name, keys, value_place_holder[:-1])
        return query, tuple(values.values())

    @classmethod
    def make_update_query(cls, table_name:str, values:dict, where_key):
        """
        Creates an update query with only chosen fields
        Supports only a single field where clause

        Args:
            table_name: a string indicating the name of the table
            values: a dict of fields and values to be inserted
            where_key: the 'where' clause field

        Returns:
            query: a SQL string with
            values: a tuple of values to replace placeholder(%s) tokens in query - except the where clause value

        """
        keys = ', '.join(values.keys())
        value_place_holder = ' %s,' * len(values)
        query = cls._update_string.format(table_name, keys, value_place_holder[:-1], where_key)
        return query, tuple(values.values())

    @classmethod
    def _get_where_clause_with_values(cls, where_keys):
        vals = []
        where_clause = ""

        for i, v in enumerate(where_keys):
            s = "("
            for k, key in enumerate(v.items()):
                if k != 0:
                    s += " and "
                s += " " + key[0]
                s += "=%s"
                vals.append(v[key[0]])

            s += ")"

            if i != 0:
                where_clause += " or "
            where_clause += s
        return where_clause, tuple(vals)

    @classmethod
    def make_delete_query(cls, table_name: str, where_keys: list):
        """
        Creates a select all query with where keys
        Supports multiple where claus with and or or both

        Args:
            table_name: a string indicating the name of the table
            where_keys: list of dictionary
            example : [{'name':'cip','url':'cip.com'},{'type':'manufacturer'}]
            where_clause will look like ((name=%s and url=%s) or (type=%s))
            multiple dictionary gets converted to or clause and elements of sam dictionary in and clause

        Returns:
            query: a SQL string with
            values: a tuple of values to replace placeholder(%s)

        """
        where_clause, values = cls._get_where_clause_with_values(where_keys)
        query = cls._delete_query.format(table_name, where_clause)
        return query, values

    @classmethod
    def make_select_selective_column_query(cls, table_name: str, columns: list, where_keys: list):
        """
        Creates a select query for selective columns with where keys
        Supports multiple where claus with and or or both

        Args:
            table_name: a string indicating the name of the table
            columns: list of columns to select from
            where_keys: list of dictionary
            example of where keys: [{'name':'cip','url':'cip.com'},{'type':'manufacturer'}]
            where_clause will look like ((name=%s and url=%s) or (type=%s))
            multiple dictionary gets converted to or clause and elements of sam dictionary in and clause

        Returns:
            query: a SQL string with
            values: a tuple of values to replace placeholder(%s)

        """
        columns_string = ", ".join(columns)
        where_clause, values = cls._get_where_clause_with_values(where_keys)
        query = cls._select_selective_column.format(columns_string, table_name, where_clause)
        return query, values

    @classmethod
    def make_select_all_query(cls, table_name: str, where_keys: list):
        """
        Creates a select all query with where keys
        Supports multiple where claus with and or or both

        Args:
            table_name: a string indicating the name of the table
            where_keys: list of dictionary
            example : [{'name':'cip','url':'cip.com'},{'type':'manufacturer'}]
            where_clause will look like ((name=%s and url=%s) or (type=%s))
            multiple dictionary gets converted to or clause and elements of sam dictionary in and clause

        Returns:
            query: a SQL string with
            values: a tuple of values to replace placeholder(%s)

        """
        where_clause, values = cls._get_where_clause_with_values(where_keys)
        query = cls._select_all_string.format(table_name, where_clause)
        return query, values


def cursor(func):
    """
    Decorator that provides a cursor to the calling function

    Adds the cursor as the second argument to the calling functions

    Requires that the function being decorated is an instance of a class or object
    that yields a cursor from a get_cursor() coroutine or provides such an object
    as the first argument in its signature

    Yields:
        A client-side cursor
    """

    @wraps(func)
    def wrapper(cls, *args, **kwargs):
        with (yield from cls.get_cursor()) as c:
            return (yield from func(cls, c, *args, **kwargs))

    return wrapper


def dict_cursor(func):
    """
    Decorator that provides a dictionary cursor to the calling function

    Adds the cursor as the second argument to the calling functions

    Requires that the function being decorated is an instance of a class or object
    that yields a cursor from a get_cursor(dict_cursor=True) coroutine or provides such an object
    as the first argument in its signature

    Yields:
        A client-side dictionary cursor
    """

    @wraps(func)
    def wrapper(cls, *args, **kwargs):
        with (yield from cls.get_cursor(dict_cursor=True)) as c:
            return (yield from func(cls, c, *args, **kwargs))

    return wrapper

