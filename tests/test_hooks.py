#!/usr/bin/env python3
"""Tests clang-format, clang-tidy, and oclint against .c and .cpp
With this snippet:

    int main() {  int i;  return 10;}

- Triggers clang-format because what should be on 4 lines is on 1
- Triggers clang-tidy because "magical number" 10 is used
- Triggers oclint because short variable name is used

pytest_generate_tests comes from pytest documentation and allows for
table tests to be generated and each treated as a test by pytest.
This allows for 45 tests with a descrition instead of 3 which
functionally tests the same thing.
"""
import difflib
import os
import re
import shutil
import subprocess as sp
import uuid

import pytest

from hooks.clang_format import ClangFormatCmd
from hooks.clang_tidy import ClangTidyCmd
from hooks.cppcheck import CppcheckCmd
from hooks.oclint import OCLintCmd
from hooks.uncrustify import UncrustifyCmd


def pytest_generate_tests(metafunc):
    """Taken from pytest documentation to allow for table tests:
    https://docs.pytest.org/en/latest/example/parametrize.html#paramexamples"""
    metafunc.cls.setup_class()
    idlist = []
    argvalues = []
    argnames = []
    for scenario in metafunc.cls.scenarios:
        idlist.append(scenario[0])
        items = scenario[1].items()
        argnames = [x[0] for x in items]
        argvalues.append([x[1] for x in items])
    metafunc.parametrize(argnames, argvalues, ids=idlist, scope="class")


def create_temp_dir_for(filename):
    """Create a temporary dir for a file, returning the file path."""
    uuid_dir = str(uuid.uuid4())
    temp_dir = os.path.join("tests/files/temp", uuid_dir)
    os.makedirs(temp_dir)
    new_temp_name = shutil.copy2(filename, temp_dir)
    return os.path.join(os.getcwd(), new_temp_name)


def assert_equal(expected, actual):
    """Stand in for Python's assert which is annoying to work with."""
    if expected != actual:
        print("Expected:`" + str(expected) + "`")
        print("Actual:`" + str(actual) + "`")
        print(
            "\n".join(difflib.ndiff(expected.split("\n"), actual.split("\n")))
        )
        pytest.fail("Test failed!")


def generate_list_tests():
    """Generate the scenarios for class (45)

    This is all the arg (6) and file (4) combinations
    +2x tests:
        * Call the shell hooks installed with pip to mimic end user use
        * Call via importing the command classes to verify expectations"""
    pwd = os.getcwd()
    err_c = os.path.join(pwd, "tests/files/err.c")
    err_cpp = os.path.join(pwd, "tests/files/err.cpp")
    ok_c = os.path.join(pwd, "tests/files/ok.c")
    ok_cpp = os.path.join(pwd, "tests/files/ok.cpp")

    ok_str = ""

    clang_format_args_sets = [[], ["-i"]]
    clang_format_err = """
<  int main(){int i;return;}
---
>  int main() {
>    int i;
>    return;
>  }
"""  # noqa: E501
    clang_format_output = [ok_str, ok_str, clang_format_err, clang_format_err]

    ct_base_args = ["-quiet", "-checks=*", "-warnings-as-errors=*"]
    # Run normal, plus two in-place arguments
    additional_args = [[], ["-fix"], ["--fix-errors"]]
    clang_tidy_args_sets = [ct_base_args + arg for arg in additional_args]
    clang_tidy_err_str = """{0}:1:18: error: non-void function 'main' should return a value [clang-diagnostic-return-type]
int main(){{int i;return;}}
                 ^
1 error generated.
Error while processing {0}.
"""  # noqa: E501
    clang_tidy_str_c = clang_tidy_err_str.format(err_c, "")
    clang_tidy_str_cpp = clang_tidy_err_str.format(err_cpp)
    clang_tidy_output = [ok_str, ok_str, clang_tidy_str_c, clang_tidy_str_cpp]

    oclint_err = """
Compiler Errors:
(please be aware that these errors will prevent OCLint from analyzing this source code)

{0}:1:18: non-void function 'main' should return a value

Clang Static Analyzer Results:

{0}:1:18: non-void function 'main' should return a value


OCLint Report

Summary: TotalFiles=0 FilesWithViolations=0 P1=0 P2=0 P3=0{1}


[OCLint (http://oclint.org) v{2}]
"""
    oclint_arg_sets = [
        ["-enable-global-analysis", "-enable-clang-static-analyzer"]
    ]
    ver_output = sp.check_output(["oclint", "--version"]).decode("utf-8")
    oclint_ver = re.search(r"OCLint version ([\d.]+)\.", ver_output).group(1)
    eol_whitespace = " "
    oclint_err_str_c = oclint_err.format(err_c, eol_whitespace, oclint_ver)
    oclint_err_str_cpp = oclint_err.format(err_cpp, eol_whitespace, oclint_ver)
    oclint_output = [ok_str, ok_str, oclint_err_str_c, oclint_err_str_cpp]

    # Specify config file as autogenerated one varies between uncrustify verions.
    # v0.66 on ubuntu creates an invalid config; v0.68 on osx does not.
    unc_base_args = ["-c", "tests/uncrustify_defaults.cfg"]
    unc_addtnl_args = [[], ["--replace", "--no-backup"]]
    uncrustify_arg_sets = [unc_base_args + arg for arg in unc_addtnl_args]
    uncrustify_err = """\n<  int main(){int i;return;}\n---\n>  int main(){\n>    int i; return;\n>  }\n"""  # noqa: E501
    uncrustify_output = [ok_str, ok_str, uncrustify_err, uncrustify_err]

    cppcheck_arg_sets = [[]]
    # cppcheck adds unnecessary error information.
    # See https://stackoverflow.com/questions/6986033
    cppc_ok = ""
    cppcheck_err = "[{}:1]: (style) Unused variable: i\n"
    cppcheck_err_c = cppcheck_err.format(err_c)
    cppcheck_err_cpp = cppcheck_err.format(err_cpp)
    cppcheck_output = [cppc_ok, cppc_ok, cppcheck_err_c, cppcheck_err_cpp]

    files = [ok_c, ok_cpp, err_c, err_cpp]
    retcodes = [0, 0, 1, 1]
    scenarios = []
    for i in range(len(files)):
        for arg_set in clang_format_args_sets:
            clang_format_scenario = [
                ClangFormatCmd,
                arg_set,
                files[i],
                clang_format_output[i],
                retcodes[i],
            ]
            scenarios += [clang_format_scenario]
        for arg_set in clang_tidy_args_sets:
            clang_tidy_scenario = [
                ClangTidyCmd,
                arg_set,
                files[i],
                clang_tidy_output[i],
                retcodes[i],
            ]
            scenarios += [clang_tidy_scenario]
        for arg_set in oclint_arg_sets:
            oclint_scenario = [
                OCLintCmd,
                arg_set,
                files[i],
                oclint_output[i],
                retcodes[i],
            ]
            scenarios += [oclint_scenario]
        for arg_set in uncrustify_arg_sets:
            uncrustify_scenario = [
                UncrustifyCmd,
                arg_set,
                files[i],
                uncrustify_output[i],
                retcodes[i],
            ]
            scenarios += [uncrustify_scenario]
        for arg_set in cppcheck_arg_sets:
            cppcheck_scenario = [
                CppcheckCmd,
                arg_set,
                files[i],
                cppcheck_output[i],
                retcodes[i],
            ]
            scenarios += [cppcheck_scenario]
    return scenarios


class TestHooks:
    """Test all C Linters: clang-format, clang-tidy, and oclint."""

    @classmethod
    def setup_class(cls):
        """Create test files that will be used by other tests."""
        os.makedirs("tests/files/temp", exist_ok=True)
        scenarios = generate_list_tests()
        cls.scenarios = []
        for test_type in [cls.run_cmd_class, cls.run_shell_cmd]:
            for s in scenarios:
                type_name = test_type.__name__
                desc = " ".join(
                    [type_name, s[0].command, s[2], " ".join(s[1])]
                )
                test_scenario = [
                    desc,
                    {
                        "test_type": test_type,
                        "cmd": s[0],
                        "args": s[1],
                        "fname": s[2],
                        "expd_output": s[3],
                        "expd_retcode": s[4],
                    },
                ]
                cls.scenarios += [test_scenario]

    @staticmethod
    def determine_edit_in_place(cmd_name, args):
        """runtime means to check if cmd/args will edit files"""
        retval = (
            cmd_name == "clang-format"
            and "-i" in args
            or cmd_name == "clang-tidy"
            and ("-fix" in args or "--fix-errors" in args)
            or cmd_name == "uncrustify"
            and "--replace" in args
        )
        return retval

    def test_run(self, test_type, cmd, args, fname, expd_output, expd_retcode):
        """Test each command's class from its python file
        and the command for each generated by setup.py."""
        # None of these commands should have overlap
        fix_in_place = self.determine_edit_in_place(cmd.command, args)
        if fix_in_place and "err.c" in fname:
            temp_file = create_temp_dir_for(fname)
            expd_output = expd_output.replace(fname, temp_file)
            fname = temp_file
        test_type(cmd, args, fname, expd_output, expd_retcode)
        if fix_in_place and "err.c" in fname:
            temp_dir = os.path.dirname(fname)
            shutil.rmtree(temp_dir)

    @staticmethod
    def run_cmd_class(cmd_class, args, fname, target_output, target_retcode):
        """Test the command class in each python hook file"""
        cmd = cmd_class([fname] + args)
        if target_retcode == 0:
            cmd.run()
        else:
            with pytest.raises(SystemExit):
                cmd.run()
                # If this continues with no system exit, print info
                print("stdout:`" + cmd.stdout + "`")
                print("stderr:`" + cmd.stderr + "`")
                print("returncode:", cmd.returncode)
        actual = cmd.stdout + cmd.stderr
        retcode = cmd.returncode
        assert_equal(target_output, actual)
        assert target_retcode == retcode

    @staticmethod
    def run_shell_cmd(cmd_class, args, fname, target_output, target_retcode):
        """Use command generated by setup.py and installed by pip
        Ex. oclint => oclint-hook for the hook command"""
        all_args = [cmd_class.command + "-hook", fname, *args]
        sp_child = sp.run(all_args, stdout=sp.PIPE, stderr=sp.PIPE)
        actual = str(sp_child.stdout + sp_child.stderr, encoding="utf-8")
        retcode = sp_child.returncode
        assert_equal(target_output, actual)
        assert target_retcode == retcode

    @staticmethod
    def teardown_class():
        """Delete files generated by these tests."""
        generated_files = ["ok.plist", "err.plist"]
        for filename in generated_files:
            if os.path.exists(filename):
                os.remove(filename)
