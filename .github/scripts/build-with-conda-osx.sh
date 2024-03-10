function startgroup {
    # Start a foldable group of log lines
    # Pass a single argument, quoted
    case ${CI:-} in
        github_actions )
            echo "::group::$1";;
        * )
            echo "$1";;
    esac
} 2> /dev/null

function endgroup {
    # End a foldable group of log lines
    # Pass a single argument, quoted

    case ${CI:-} in
        github_actions )
            echo "::endgroup::";;
    esac
} 2> /dev/null

set -xe

MINIFORGE_HOME=${MINIFORGE_HOME:-${HOME}/miniforge3}

( startgroup "Installing a fresh version of Miniforge" ) 2> /dev/null

MINIFORGE_URL="https://github.com/conda-forge/miniforge/releases/latest/download"
MINIFORGE_FILE="Mambaforge-MacOSX-$(uname -m).sh"
curl -L -O "${MINIFORGE_URL}/${MINIFORGE_FILE}"
rm -rf ${MINIFORGE_HOME}
bash $MINIFORGE_FILE -b -p ${MINIFORGE_HOME}

( endgroup "Installing a fresh version of Miniforge" ) 2> /dev/null

( startgroup "Configuring conda" ) 2> /dev/null

source ${MINIFORGE_HOME}/etc/profile.d/conda.sh
conda activate base
export CONDA_SOLVER="libmamba"
export CONDA_LIBMAMBA_SOLVER_NO_CHANNELS_FROM_INSTALLED=1

mamba install --update-specs --quiet --yes --channel conda-forge libsecp256k1 pkg-config

( endgroup "Configuring conda" ) 2> /dev/null