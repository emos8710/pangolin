#!/usr/bin/env python3

import argparse
import collections
from Bio import AlignIO
import os
cwd = os.getcwd()

"""
Current output:
--mask-out
lineage,snp,taxon
B,2897GT,WH0X/Taxon/Name

--defining-snps-out
lineage,defining_snps
B,2897GT;30000TA

--representative-seqs-out
lineage,name
B,WH0X/Taxon/Name
"""


def parse_args():
    parser = argparse.ArgumentParser(description='Find all snps.')

    parser.add_argument("-a", action="store", type=str, dest="a")
    parser.add_argument("-l", action="store", type=str, dest="l")

    parser.add_argument("--representative-seqs-out", action="store", type=str, dest="representative_out")
    parser.add_argument("--defining-snps-out", action="store", type=str, dest="defining_out")
    parser.add_argument("--mask-out", action="store", type=str, dest="mask_out")
    parser.add_argument("--defining-cut-off", action="store", type=float, default=90,dest="def_cutoff")
    parser.add_argument("--represent-cut-off", action="store", type=float,default=10,dest="rep_cutoff")
    return parser.parse_args()

def get_lineage_dict(alignment, lineage_file):
    """Takes in lineage annotations and an alignment file. 
    Outputs structured dict of seq records per lineage."""
    
    lineages_dict = {}
    lineages_records = collections.defaultdict(list)
    sorted_by_n_lineages = {}
    with open(lineage_file, "r") as f:
        for l in f:
            l = l.rstrip("\n")
            tokens = l.split(",")
            lineages_dict[tokens[0]]=tokens[1]
    not_in_csv = []
    c= 0
    for record in alignment:
        if record.id != "Wuhan/WH04/2020":
            if record.id in lineages_dict:
                lineage = lineages_dict[record.id]
                lineages_records[lineage].append(record)
                c+=1
            else:
                not_in_csv.append(record.id)
    print(f"{c} sequences added to lineages_records")
    print(f"Note: The following {len(not_in_csv)} sequences were found in alignment but not lineages csv file")
    for seq in not_in_csv:
        print(seq)
    for lineage in lineages_records:
        sorted_records = sorted(lineages_records[lineage], key = lambda x : x.annotations["pcent_N"])
        sorted_by_n_lineages[lineage] = sorted_records

    print("Lineage\t\tNum sequences")
    for lineage in sorted(sorted_by_n_lineages):
        print(f"{lineage}\t\t{len(sorted_by_n_lineages[lineage])}")
    
    return sorted_by_n_lineages

def find_snps(ref,member):
    """Identifies unambiguous snps between two sequences 
    and returns them as a list, using position in the ref seq (i.e. no gaps in ref)"""
    snps = []
    index = 0 
    for i in range(len(ref)):
        if ref[i]!= '-':
            index +=1
            
        col = [ref[i],member[i]]
        if len(set(col))>1:
            if not col[1].lower() in ["a","g","t","c","-"]:
                pass
            else:
                snp = f"{index}{col[0].upper()}{col[1].upper()}"
                snps.append(snp)
    return snps

def get_reference(alignment,reference_id="Wuhan/WH04/2020"):
    """get reference seq record"""
    for record in alignment:
        if record.id == reference_id:
            return record

def pcent_done(c, total):
    return round((c*100)/total, 2)

def add_snps_annotation(alignment, reference):
    """add list of snps relative to ref as an annotation to the seq record"""
    c = 0
    total = len(alignment)
    for record in alignment:
        c +=1 
        if c%500==0:
            print(pcent_done(c, total), '%')

        snps = find_snps(reference.seq, record.seq)
        record.annotations["snps"] = snps
        snp_string =snp_list_to_snp_string(snps)
        record.annotations["snp_string"] = snp_string

    print(total, "records annotated")

def add_N_annotation(alignment):
    """add pcent_N as an annotation to the seq record"""
    for record in alignment:
        pcent_N = get_N_content(record.seq)
        record.annotations["pcent_N"] = pcent_N
    print(len(alignment), "records annotated")
        
def get_N_content(seq):
    """return the percentage N content for a given seq"""
    num_N = str(seq).upper().count("N")
    pcent_N = (num_N*100)/len(seq)
    return pcent_N

def get_singleton_snps(lineage, snp_counter):
    """Returns a list of snps that only appear 
    once within a given lineage, will be masked"""
    singletons = []
    for snp in snp_counter:
        if len(snp_counter[snp]) == 1:
            singletons.append((lineage, snp, snp_counter[snp][0]))
    return singletons

def get_inclusion_pcent(snp,snp_counter,total_in_lineage):
    """return the percentage of taxa within a lineage that 
    have a given snp. E.g. if all taxa have that snp ==100, 
    if 3 taxa out of 12 have that particular snp, will return 25 etc."""
    num_taxa_with_snp = len(snp_counter[snp])
    inclusion_pcent = (100*num_taxa_with_snp)/total_in_lineage
    return inclusion_pcent

def get_represented_and_defining_snps(singletons, snp_counter, lineages_dict, defining_cut_off, represent_cut_off,lineage):
    """based on cut offs, will return a list containing snps that are present
    at a lineage defining level and a list containing snps that are present at 
    a should-be-represented-in-the-tree level"""
    defining = []
    flagged = []
    total_in_lineage = len(lineages_dict[lineage])
    for snp in snp_counter:
        singleton = False
        for s in singletons:
            s_snp = s[1]
            if snp == s_snp:
                singleton = True

        if not singleton:
            inclusion_pcent = get_inclusion_pcent(snp,snp_counter,total_in_lineage)

            if inclusion_pcent > defining_cut_off:
                defining.append(snp)
            if inclusion_pcent > represent_cut_off:
                flagged.append(snp)

    return defining, flagged

def get_ids_in_list_of_records(records):
    """return ids in a set of seq records"""
    ids = []
    for record in records:
        ids.append(record.id)
    return ids

def get_representative_taxa(lineage,lineage_snps,lineages_dict, flagged):
    """for each set of snps in the lineage snp dict, get the record 
    with the lowest n content that has that snp pattern. 
    for each snp in that set of snps, if it was flagged that it should be 
    represented in the guide tree, but hasn't been included yet, include that record
    and note the snps the record has contributed to the tree. 
    return the set of records that fulfill the representation needed."""
    represented= []
    taxa = []
    for snp_set in lineage_snps:

        records_sorted_by_N = sorted(lineage_snps[snp_set], key = lambda x : int(x[1]))
        lowest_N = records_sorted_by_N[0][0]

        snps = snp_set.split(";")
        
        for snp in snps:
            if snp in flagged and not snp in represented:
                
                represented.append(snp)

                for record in lineages_dict[lineage]:
                    if record.id == lowest_N:
                        snps_in_lowest_N = record.annotations["snps"]
                        for lowest_N_snp in snps_in_lowest_N:
                            represented.append(snp)
                            taxa_ids = get_ids_in_list_of_records(taxa)
                            if record.id not in taxa_ids:
                                taxa.append(record)

    return taxa

def pad_taxa_to_5(taxa, lineages_dict, lineage):
    """if you have filled the representatives needed but dont have 
    very many taxa, pad that list to five for the craic"""
    pre_len = len(taxa)
    if pre_len < 3:
        for record in lineages_dict[lineage]:
            if len(taxa)<3:
                taxa_ids = get_ids_in_list_of_records(taxa)
                if record.id not in taxa_ids:
                    taxa.append(record)
            else:
                pass
        else:
            pass
    print(f"\t5f. {lineage}: {pre_len} padded to {len(taxa)} representative seqs")   
    return taxa
     
def snp_list_to_snp_string(snp_list):
    """turn a snp list into a `;`-separated string of snps that are sorted by 
    position in the genome"""
    snp_string = ";".join(sorted(snp_list, key = lambda x : int(x[:-2])))
    return snp_string

def get_all_snps(alignment_file,lineage_file,outfile,defining_cut_off,represent_cut_off):
    """ this is the main worker function of this script. 
    ultimately it returns a list of singleton snps to_mask
    and a list of lineage_defining_snps per lineage to write to a file

    1. reads in the alignment
    2. identifies the reference sequence
    3. adds in some useful things to the seq record (n, snps, snp_string)

    4. structures alignment records by lineage
    5. for each lineage
        - count occurences of each snp and id singletons to mask
        - make dict keyed by unique snp combinations with all the associated records as value list
        - get snps to be represented in the tree and potential defining snps (by % cut off args)
        - get best taxa to represent the snps to be represented based on N content
        - if theres too few taxa for each lineage add some more (total of 5)
        - write representatives 
        - get a set of snps that 100 of taxa are in
        - if snp set is empty, pad with snps flagged as potential defining snps by the less strict cut off
    6. return to_mask and lineage_defining_snps
    """
    print("1. Reading in the alignment")
    aln = AlignIO.read(alignment_file, "fasta")
    print("2. Getting the reference:")
    reference = get_reference(aln)
    print(reference.id)
    print("3a. Annotating N content onto seq records")
    add_N_annotation(aln)
    print("3b. Annotating snps onto seq records")
    add_snps_annotation(aln, reference)
    print("4. Making lineages dict")
    lineages_dict = get_lineage_dict(aln, lineage_file)
    
    to_mask = []
    lineage_defining_snps = []

    for lineage in sorted(lineages_dict):
        lineage_snps = collections.defaultdict(list)
        snp_counter = collections.defaultdict(list)

        for record in lineages_dict[lineage]:

            snps = record.annotations["snps"]
            snp_string = record.annotations["snp_string"]
            pcent_N = record.annotations["pcent_N"]

            for i in snps:
                snp_counter[i].append(record.id)

            lineage_snps[snp_string].append((record.id,pcent_N))
        print("5. Lineage",lineage)
        print(f"\t5a. Made lineage_snps")
        print(f"\t5b. Counted up {len(snp_counter)} snps")
        singletons = get_singleton_snps(lineage, snp_counter)
        print(f"\t5c. Identified {len(singletons)} singletons in {lineage}")
        for singleton in singletons:
            to_mask.append(singleton)

        defining,flagged = get_represented_and_defining_snps(singletons, snp_counter, lineages_dict, defining_cut_off,represent_cut_off,lineage)
        print(f"\t5d. Identified {len(defining)} potential defining snps in {lineage}")
        print(f"\t5e. Flagged {len(flagged)} snps to be represented in {lineage}")
        taxa = get_representative_taxa(lineage,lineage_snps,lineages_dict, flagged)

        taxa = pad_taxa_to_5(taxa, lineages_dict, lineage)

        for record in taxa:
            snp_string = record.annotations["snp_string"]
            outfile.write(f"{lineage},{record.id}\n")
        
        defining_snps = list(set.intersection(*[set(x.split(";")) for x in lineage_snps]))

        if defining_snps == []:
            for snp in defining:
                defining_snps.append(snp)

        lineage_str = snp_list_to_snp_string(defining_snps)
        print(f"{lineage} defining snps: {lineage_str}")   
        lineage_defining_snps.append((lineage, lineage_str))
        
    return to_mask, lineage_defining_snps

def read_alignment_and_write_files():

    args = parse_args()

    alignment_file = os.path.join(cwd, args.a)
    if not os.path.exists(alignment_file):
        sys.stderr.write('Error: cannot find alignment file at {}\n'.format(alignment_file))
        sys.exit(-1)
    else:
        print(f"Reading in alignment file {alignment_file}.")

    lineage_file = os.path.join(cwd, args.l)
    if not os.path.exists(lineage_file):
        sys.stderr.write('Error: cannot find lineage file at {}\n'.format(lineage_file))
        sys.exit(-1)
    else:
        print(f"Reading in lineage annotations file {lineage_file}.")
    
    defining_cut_off = args.def_cutoff
    represent_cut_off = args.rep_cutoff
    
    fw = open(args.representative_out, "w")
    fw.write("lineage,name\n")
    to_mask,lineage_defining_snps = get_all_snps(alignment_file,lineage_file,fw,defining_cut_off,represent_cut_off)
    fw.close()
    print("6. Writing mask, representatives and defining snps files.")
    with open(args.mask_out,"w") as fm:
        fm.write("lineage,snp,taxon\n")
        for snp in to_mask:
            lineage,snp,taxon = snp
            fm.write(f"{lineage},{snp},{taxon}\n")

    with open(args.defining_out,"w") as fd:
        fd.write("lineage,defining_snps\n")
        
        for defining_snps in lineage_defining_snps:
            lineage,lineage_str = defining_snps
            fd.write(f"{lineage},{lineage_str}\n")


if __name__ == '__main__':

    read_alignment_and_write_files()