find_package(ZLIB REQUIRED)
build_exec(
  EXECNAME m6-energy-transition
  SOURCE_FILES m6-energy-transition.cc
  LIBRARIES_TO_LINK "${ns3-libs}" "${ns3-contrib-libs}" ${ZLIB_LIBRARIES}
  EXECUTABLE_DIRECTORY_PATH ${CMAKE_OUTPUT_DIRECTORY}/scratch/m6-energy
)
