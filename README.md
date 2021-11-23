# Snowflake CICD utility

Python based **CICD** tool for for managing Snowflake databases.

**Table of contents:**

1. [Installation](#installation)
2. [Configuration](#configuration)
3. [Usage](#usage)
4. [Work cycle](#work-cycle)
5. [Use cases](#use-cases)
6. [How it works](#how-it-works)
7. [Troubleshooting](#troubleshooting)

<a name="installation"></a>
## Installation

#### 1. Install Python

Make sure that `python3` executable is present in your path:

```sh
$ python3
Python 3.7.7 (default, Mar 10 2020, 15:43:33)
[Clang 11.0.0 (clang-1100.0.33.17)] on darwin
Type "help", "copyright", "credits" or "license" for more information.
>>>
```

Deployment script won't work with Python2!

#### 2. Install python dependencies

This should be as easy as running:

```sh
$ python3 -m pip install -r requirements.txt
```

Of course you can use `pip` instead, but this way it easier to make sure the packages will be installed in a proper location.

Feel free to use one of Python's environment managers.

<a name="configuration"></a>
## Configuration

Current version supports [Key Pair Authentication](https://docs.snowflake.com/en/user-guide/python-connector-example.html#using-key-pair-authentication) with Snowflake. Only unencrypted keys are supported! There is an undocumented username+password method but should not be used.

If you have your key pair already generated you can jump to section **3**.

#### 1. Generate key pair

Generate unencrypted private key:

```sh
$ openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out [username]_snowflake.p8 -nocrypt
```

Now generate the public key by referencing the private key:

```sh
$ openssl rsa -in [username]_snowflake.p8 -pubout -out [username]_snowflake.pub
```

Assign the public key to the Snowflake user using ALTER USER. Run the query using your Snowflake's client:

```sql
alter user [username] set rsa_public_key='MIIBIjANBgkqh...
WbyzHiMVJw8u+...
xwIDAQAB';
```

To fill in the `rsa_public_key` part you have to copy `[username]_snowflake.pub` file contents and paste it in SQL console.

**Note:** You have to remove `-----BEGIN PUBLIC KEY-----` and `-----END PUBLIC KEY-----` lines from public key in your SQL query.

Now place your keys in a safe location. For Linux and OSX this can be for example:

```sh
$ mv [username]_snowflake.* ~/.ssh/
```

#### 2. Prepare data model repository

Prepare (or reuse existing) GIT repository that holds data model.

If you don't have one, you can follow this procedure:

```sh
# you are in `snowflake-cicd` folder
$ cp -r model-repo-sample ../data_model
$ cd ../data_model
$ git init
```

#### 3. Update configuration file

Go to your model GIT repository, and open `.snowflake-cicd.ini` file:

```sh
# you are in `snowflake-cicd` folder
$ cp snowflake-cicd.ini ~/.snowflake-cicd.ini
$ edit .snowflake-cicd.ini
```

In the `.snowflake-cicd.ini` file you have to fill in at least two fields: `user` and `private_key`.

<a name="usage"></a>
## Usage

You can run `cicd` without arguments to see help:

```sh
$ cicd
usage: cicd [-h] [-v] [-t] [-f]
                 {abandoned,clone,compare,deploy,diff,history,migrate,prepare,sync,test_sync}
                 [{abandoned,clone,compare,deploy,diff,history,migrate,prepare,sync,test_sync} ...]

Git <-> Snowflake sync and automatic deployment.

Actions:

  prepare               Prepares release candidate file.
  deploy                Deploys changes from release candidate file.
  migrate               prepare + deploy 
  validate              Validates all .sql files in model directory
  history               Prints release history.
  clone                 Clones (or replaces) database based on prod.
  sync                  Syncs unapplied changes from model and releases dirs.
  test_sync             Test release on a separate clone (run it before creating pull request).
  compare               Compares Snowflake and current branch DDLs.
  diff                  Prints diff from production.
  abandoned             Compares active branches and development clones.

positional arguments:
  {prepare,deploy,migrate,validate,history,clone,sync,test_sync,compare,diff,abandoned}
                        Action to run
                        Action to run

optional arguments:
  -h, --help            show this help message and exit
  -v, --verbose         Verbose mode. Shows SQL statements.
  -t, --dry-run         Show SQL to be executed, but doesn't run it.
  -f, --force           Force command without yes/no question asked in terminal.
  --file [FILE]         Filename for compare action
```

<a name="actions"></a>
### Actions

<a name="abandoned"></a>
#### `abandoned`

Compares active development branches and database clones. It does so by querying all the databases `LIKE '_DEV%'` in `INFORMATION_SCHEMA.DATABASES`. For each clone found it is searching for a corresponding branch.

<a name="branch-clone-mapping"></a>Branch names are converted to database clone names this way:

1. Uppercase
2. Replace all non-words characters (`\W`) with underscore (`_`)
3. Take first 30 chars
4. Add prefix `_DEV_`

This way branch `feature/DW-1249-create-pre-deploy-and-post-deploy-tests` is mapped to `_DEV_FEATURE_DW_1249_CREATE_PRE_DEP`.

**`abandoned` example output:**

```
|____________clone_____________|_____created______|_____updated______|_has branch?__|
| _DEV_DW_1336_CREATE_A_SAMPLE | 2020-04-20 17:18 | 2020-04-20 17:19 |      no      |
| _DEV_FEATURE_A               | 2020-04-22 12:04 | 2020-04-22 12:06 |      no      |
| _DEV_FEATURE_SQL_QUERIES_IN_ | 2020-04-23 19:27 | 2020-04-23 19:29 |      no      |
| _DEV_FEATURE_DW_1249_CREATE_ | 2020-04-24 23:13 | 2020-04-24 23:14 |     yes      |
```

Database clones with `no` in the last column (`has branch?`) should be dropped.

<a name="clone"></a>
#### `clone`

Clones (or replaces) database based on production. New clone is created based on active branch name (see [branch to clone mapping](#branch-clone-mapping) in [abandoned](#abandoned) action to learn how branch name is mapped to clone name). Due to this it is impossible to run `clone` on main branch (**CICD** will refuse to run).

If target clone does not exist the action will perform immediately. If target clone exists **CICD** will ask for confirmation before running. This behavior can be overwritten by `--force` flag.

**`clone` example output:**

```
Checking if _DEV_FEATURE_A already exists...
_DEV_FEATURE_A already exists. Are you sure you want to replace it (y/n): y
Cloning DWH into _DEV_FEATURE_A
Cloning finished
```

Example run on `main` branch:
```
Trying to create new database with name dwh...
```

<a name="compare"></a>
#### `compare`

Compare allows you to list all the objects modified in your cloned database since cloning. The comparison is made purely on a database level. Even if altered an object manually on the server (ignoring GIT and releases history table) the object will be listed.

Technically compare list all the objects from `INFORMATION_SCHEMA`.`[TABLES|FUNCTIONS|FILE_FORMATS|EXTERNAL_TABLES|PIPES|PROCEDURES|SEQUENCES|STAGES|VIEWS]` looking for those with `LAST_ALTERED` greater than current clone creation time (+1 minute).

Comparison algorithm assumes the object was changed in both situation: it's definition has changed or it contents has changed (in case of a table).

**`compare` example output:**

```
|___schema___|__________object name___________|____type____|___last change____|
|     PUBLIC . dwh_releases_history           |   TABLE    | 2020-04-12 15:42 |
|        RAW . lnk_event_sess                 |   TABLE    | 2020-04-12 15:42 |
|        RAW . hub_event                      |   TABLE    | 2020-04-12 15:42 |
|         DM . dim_page                       |    VIEW    | 2020-04-12 15:42 |
|        RAW . load_hub_session               | PROCEDURE  | 2020-04-12 15:42 |
|        BIZ . sat_event                      |    VIEW    | 2020-04-12 15:42 |
```

In the example above all the listed objects were somehow altered after the clone was created. All the (beside `dwh_releases_history`) should be included in release file.

<a name="deploy"></a>
#### `deploy`

Deploys changes from release candidate file.

<a name="diff"></a>
#### `diff`

Show all the changes in `model` folder between current branch and `main`. Technically it runs:

```
$ git diff --color=always main model
```

**`diff` example output:**

```diff
diff --git a/model/DV_Layers/dm/Dimension/tables/dim_time.sql b/model/DV_Layers/dm/Dimension/tables/dim_time.sql
index c9a758c..3303895 100644
@@ -2,7 +2,7 @@ CREATE TABLE dm.dim_time
        sk_time varchar(4) PRIMARY KEY NOT NULL,
        time_of_day     varchar(8) NOT NULL,
-       hour_of_day varchar(2) NOT NULL,
+       hour_of_day varchar(4) NOT NULL,
        minute_of_hour varchar(2) NOT NULL
```

<a name="history"></a>
#### `history`

This action displays a comparison of all the releases applied in on clone and production. It works only on a database level. Use [diff](#diff) action if you want to see the comparison on GIT level.

Technically the comparison is done by comparing entries in tables `PUBLIC.DWH_RELEASES_HISTORY` both in the production database, and cloned database.

**`history` example output:**

```
|_commit hash_|___________file name____________|__applied by__|____applied on____|branch|_prod_|
| bc2cbffee0  | <<init>>                       |     USER     | 2020-04-05 15:16 |  •   |  •   |
| 84d474c10a  | lites/views/view_sat_event.sql |     USER     | 2020-04-08 14:55 |  •   |  •   |
| dffcae544d  | imension/views/dim_browser.sql |     USER     | 2020-04-08 14:56 |  •   |  •   |
| dc84b4ac53  | m/Dimension/views/dim_page.sql |     USER     | 2020-04-08 14:56 |  •   |  •   |
| 0b66beaeac  | releases/fact_visits.sql       |     USER     | 2020-04-08 14:56 |      |  •   |
| 4f79836a92  | releases/dim_page.sql          |     USER     | 2020-04-08 14:57 |  •   |      |
```

In the example above we can see that:

1. Release file named `releases/dim_page.sql` was applied only in our branch. Most likely this is something we did in our branch.
2. Release file named `releases/fact_visits.sql` was applied on production but not applied in our clone. There are two possible ways of syncing with production:
  a. Faster: apply this missing release file by running [sync](#sync) action.
  b. Safer: run [clone](#clone) again to get a fresh copy of production.


<a name="migrate"></a>
#### `migrate`

This is an equivalent of:

```sh
$ cicd prepare deploy
```

In other words it prepares `releases/release_candidate.sql` file first, and then releases it. This can work only if you are making safe changes (as described in [prepare](#prepare) action).

<a name="prepare"></a>
#### `prepare`

Prepares release candidate file. Let's assume we are on a branch `feature/a` and we already [cloned](#clone) database into `_DEV_FEATURE_A` (as described in [branch to clone mapping](#branchclonemapping)). Prepare works this way:

1. Getting latest applied commit in a current clone. It's as simple as selecting the latest `COMMIT` from `_DEV_FEATURE_A.PUBLIC.DWH_RELEASES_HISTORY`.
2. Getting all the modified (renamed, removed, added) files in `model` folder. These files were not yet applied on current clone.
3. Creating the file: `releases/release_candidate.sql`. This file has a recipe on how to apply changes on clone. Additionally `releases/release_candidate.sha` file is created with `release_candidate.sql` checksum inside.

`release_candidate.sql` file contains entries in this form:

```SQL
--.Release candidate file, branch: feature_a

--.File was changed but *will not be* included in the release.
-- [M] NOT_INCLUDED:model/DV_Layers/dm/Dimension/tables/dim_time.sql
--.DIFF: @@ -5 +5 @@ CREATE TABLE dm.dim_time
--.DIFF: -	hour_of_day varchar(2) NOT NULL,
--.DIFF: +	hour_of_day varchar(3) NOT NULL,

   You may need to include an ALTER TABLE statement to properly sync database state:
   ALTER TABLE DM.DIM_TIME <<HERE>>;

--.File was changed and will be included in the release.
--.You can change the order of the INCLUDE: statement below.
-- [M] INCLUDED:model/DV_Layers/dm/Dimension/views/dim_event_la.sql
```

As you can see each modified (renamed, removed, added) leaves an entry in `release_candidate.sql`. There are two main types of entries:

<a name="safe-changes"></a>
##### Safe changes

Safe changes are those that can be applied without any additional attention. These are:

* newly created files
* modified files with objects other that tables and streams

You can easily notice that view `dim_event_la.sql` is a safe change. Updated view definition can be easily applied on the server. There are two easy ways of detecting safe changes:

1. By looking at `INCLUDED:` keyword in file description line
2. By having no non-comment lines below the entry. Notice that there is nothing below `[M] INCLUDED:model/.../dim_event_la.sql`

In most of the cases you don't have to do anything with this entries. Exceptions are:

1. This is a table or stream object definition that you already added into production database.

    In this case you should change keyword `INCLUDE` to `NOT_INCLUDE` to avoid table/stream definition being executed. 
2. The order or `INCLUDE` statements is wrong.

    In this case you shoud reorder the entries accordingly. You have to be careful with lines with filenames. Those starting from `--.` are comments that can be ignored.

<a name="unsafe-changes"></a>
##### Unsafe changes

Unsafe changes are:

* modified or renamed files with table or stream definition
* removed files with objects of any type definition

You can easily notice that table `dim_time.sql` is **not** a safe change. Updated table definition can not be easily applied on the server. You have to prepare a proper `ALTER TABLE` statement. There are two easy ways of detecting unsafe changes:

1. By looking at `NON_INCLUDED:` keyword in file description line
2. By having a non-comment lines below the entry. Notice the sentences below `[M] INCLUDED:model/.../dim_time.sql`

Your job here is to replace the suggestion and sample code generated by **CICD** and fill it in with a valid SQL statement (if necessary). In the example above we should replace:

```sql
   You may need to include an ALTER TABLE statement to properly sync database state:
   ALTER TABLE DM.DIM_TIME <<HERE>>;
```
with:
```sql
ALTER TABLE DM.DIM_TIME CHANGE hour_of_day hour_of_day varchar(3) NOT NULL;
```

To make this process easier you have a difference highlighted. Notice lines starting from `--.DIFF:`

```diff
@@ -5 +5 @@ CREATE TABLE dm.dim_time
-	hour_of_day varchar(2) NOT NULL,
+	hour_of_day varchar(3) NOT NULL,
```

<a name="sync"></a>
#### `sync`

Sync performs all the missing releases in `releases` folder and run them against the database. It is somehow similar to `prepare` but it scans `releases` folder (with already prepared releases) instead of raw `model` folder.

Syncing can be necessary if you merge changes from other branch (including `main`) into your branch. Imagine this scenario:

1. You branched out to `feature/a` and created already a release file `releases/feature_a.sql`.
2. Other person was working on a `feature/b`, created `releases/feature_b.sql` and merge it to `main`.
3. You decided to `git merge` before creating a pull request. This created `releases/feature_b.sql` in your repository. You have two options (as described in [history](#history) action):
  a. Faster: apply this missing release file by running [sync](#sync) action.
  b. Safer: run [clone](#clone) again to get a fresh copy of production.

**`sync` example output:**

```
  [A] releases/feature_DW-1249-create-pre-deploy-and-post-deploy-tests.sql
Syncing changes:
Running release file releases/feature_DW-1249-create-pre-deploy-and-post-deploy-tests.sql:
   'DWH_RELEASES_HISTORY was sucesfully created',
New entry in release history table with d31197261424b6c96ae7b8d31fcc1ac9220f934b
```

<a name="test_sync"></a>
#### `test_sync`

Test sync combines three operations in one action:

1. Creates a fresh clone of production database. This clone has a new name made out last commit SHA, not branch name. This way it's independent from all you existing changes.
2. Syncs all the unsynchronized releases in `releases` directory.
3. Drops clone created in step 1.

This step is useful for testing your changes before creating a pull-request. It ensures your release file is deployable on production.

**`test_sync` example output:**

```
Cloning DWH into _DEV_26FC3058369ACECB30C48A9C69FB47
Cloning finished
   [A] releases/feature_DW-1249-create-pre-deploy-and-post-deploy-tests.sql
Syncing changes:
Running release file releases/ feature_DW-1249-create-pre-deploy-and-post-deploy-tests.sql:
   'DWH_RELEASES_HISTORY was sucesfully created',
 New entry in release history table with d31197261424b6c96ae7b8d31fcc1ac9220f934b
 Dropping clone _DEV_26FC3058369ACECB30C48A
```

#### Optional arguments

##### `--help`

Displays help message. Running **CICD** without arguments will also cause the script to show help.

<a name="verbose"></a>
##### `--verbose`

Use `--verbose` or `-v` to display more details. It enables debugging messages and print-outs all the SQL queries being raised against Snowflake.

##### `--dry-run`

Use `--dry-run` or `-t` with [deploy](#deploy) or [sync](#sync) actions to preview the release SQL to be performed. Has no impact on other actions.

##### `--force`

Use `--force` or `-f` to:

1. Ignore question _Clone already exists. Are you sure you want to replace it_ while running [clone](#clone) action.
2. Bypass error _releases/release_candidate.sql was changed or you changed branch, can't create new release candidate._ In this case it the file will be overwritten.

<a name="work-cycle"></a>
### Work cycle

#### 1. Create branch

Start from branching out from main branch. It's usually `main` but it doesn't have to. You can branch out from other active branch.

You can branch-out using Jira, Bitbucket or command line. In all the examples below we are going to use command line and we are going to work on branch `feature/a`.

```sh
# checking active branch
$ git status
On branch main
[...]
# making sure we have all the latest changes
$ git pull
# branching out
$ git checkout -b feature/a
```

#### 2. Clone database

We have a branch to work on. Now we need a fresh clone of production to have a safe destination of all our changes.

Clone database into new `_DEV_FEATURE_A` with:

```sh
$ cicd clone
```

(read more about [cloning](#clone))

Now we have a new branch `feature/a` and new development clone `_DEV_FEATURE_A`. Both equal to production.

#### 3. Modify and deploy changes

Work on files in the `model/` folder and [migrate](#migrate) all the changes with:

```sh
$ cicd migrate
```

[Migrate](#migrate) is actually running two tasks: [prepare](#prepare) followed by [deploy](#deploy). The second step can raise an error if you made an [unsafe change](#unsafe-changes). It usually happens the moment you changed table or stream, or you dropped a file from `model` folder.

In this case the script raises an error:

```
Code placeholder (<<HERE>>) found in the release candidate file.
```

You have to manually change the `releases/release_candidate.sql` file as described in [unsafe changes](#unsafe-changes) section. Once done you can repeat the second step with:

```sh
$ cicd deploy
```

You should notice that while you modify files in `model` folder and deploy your changes in your clone, there is a new file being updated after each action. It's `releases/feature_a.sql` file. This file holds all the changes you've made.

#### 4. Check your changes

You are give three ways to check your changes. Let's start from source code level.

To preview detailed [diff](#diff) of your branch against production run:

```sh
$ cicd diff
```

You can also compare all the releases applied on your clone and compare the with production by running [history](#history) action:

```sh
$ cicd history
```

The last option to examine your changes is it preview all the objects definitions changed in your cloned database since it's creation. To do so run [compare](#compare):

```sh
$ cicd compare
```

#### 5. Test your changes

Before submitting a pull-request test your changes against a fresh copy of your database. There is a command that automates all the steps. It [test_sync](#test_sync):

```sh
$ cicd test_sync
```

If it's all good you are ready to create a pull-request!

<a name="#use-cases"></a>
### Use cases

#### 1. Changing object definition

All situations in which you modify an object DDL. This including renaming the object (and a corresponding file).

##### a) [safe changes](#safe-changes)

This is the simplest scenario. Open any `.sql` file under `model/` folder and perform changes. Then run:

```sh
$ cicd migrate
```

The script will detect the change and reapply it on the server. 

##### b) [unsafe changes](#unsafe-changes)

Change table or stream definition in the `model/` folder and commit your changes. Then run:

```sh
$ cicd prepare
```

Open the `releases/release_candidate.sql` file. You will notice that the changed table is listed in the release_candidate text, and you have to manually add a proper `ALTER TABLE` SQL statement.

Once done run:

```sh
$ cicd deploy
```

#### 2. Adding a new object

It's as simple as adding a new file into `model/` folder,  and commiting your changes, and running:

```sh
$ cicd migrate
```

This works regardless the type of new object.

#### 3. Dropping an object

Remove a file from the `model/` folder and commit your changes. Then run:

```sh
$ cicd prepare
```

Open the `releases/release_candidate.sql` file. You will notice that the dropped file is listed in the release_candidate text, and you have to manually add a proper `DROP OBJECT` SQL statement.

Once done run:

```sh
$ cicd deploy
```

#### 4. Altering a database state

All the other SQL statements that are not tracked in the `model/` folder can be also applied and tracked. To do so simply run:

```sh
$ cicd prepare
```

This will generate an empty `releases/release_candidate.sql` file. Open it and add any SQL code you like.

Once done run:

```sh
$ cicd deploy
```

<a name="#how-it-works"></a>
## How it works

It's explained partially in the [Actions](#actions) section.

<a name="#troubleshooting"></a>
## Troubleshooting

In most of the situations **CICD** is not leaving you alone. It explains what went wrong and what you can do about it.

For example if you start working on `model` folder before cloning, script will suggest you doing so the moment you run [prepare](#prepare) for the first time.

If your deployment script failed, the script will print out the exact SQL statement that failed, allow you to fix it and [deploy](#deploy) again.

In other cases adding [--verbose](#verbose) can be useful.

<!--
vim:spelllang=en
-->
